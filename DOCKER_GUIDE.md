# Docker Deployment Guide

## Overview
This project includes Docker configurations for both development and production environments.

## Files
- `Dockerfile` - Container image definition
- `docker-compose.yml` - Development configuration
- `docker-compose.prod.yml` - Production configuration

## Prerequisites
1. Install Docker Desktop for Windows
2. Create `.env` file with required variables:
   ```env
   OPENAI_API_KEY=your_api_key_here
   ```

## Development Usage

### Build and Start
```bash
# Build the image
docker-compose build

# Start services (with logs)
docker-compose up

# Start in background (detached mode)
docker-compose up -d
```

### View Logs
```bash
# Follow all logs
docker-compose logs -f

# Follow API logs only
docker-compose logs -f api
```

### Stop Services
```bash
# Stop and remove containers
docker-compose down

# Stop, remove containers, and delete volumes
docker-compose down -v
```

### Rebuild After Changes
```bash
# Rebuild and restart
docker-compose up --build

# Or rebuild specific service
docker-compose build api
docker-compose up api
```

### Development Features
- **Hot-reload enabled** - Code changes automatically restart the server
- **Volume mounting** - Local code changes reflected immediately
- **Port 8000** - API accessible at http://localhost:8000

## Production Usage

### Build and Deploy
```bash
# Build production image
docker-compose -f docker-compose.prod.yml build

# Start in production mode
docker-compose -f docker-compose.prod.yml up -d
```

### Monitor Production
```bash
# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Check health status
docker-compose -f docker-compose.prod.yml ps

# View resource usage
docker stats compliance_api_prod
```

### Update Production
```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.prod.yml up --build -d

# Verify health
curl http://localhost:8000/health
```

### Production Features
- **4 worker processes** - Better performance for concurrent requests
- **No hot-reload** - Stable production environment
- **Always restart** - Auto-recovery from failures
- **Resource limits** - CPU and memory constraints
- **Health checks** - Automatic container health monitoring

## Accessing the API

### Endpoints
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health
- **Compliance Check**: http://localhost:8000/check_compliance

### Test the API
```bash
# Check health
curl http://localhost:8000/health

# Run test script (from host machine)
python test_api.py
```

## Troubleshooting

### Container won't start
```bash
# Check logs for errors
docker-compose logs api

# Check if port 8000 is already in use
netstat -ano | findstr :8000

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up
```

### Environment variables not loading
```bash
# Verify .env file exists
dir .env

# Check environment inside container
docker-compose exec api env | findstr OPENAI
```

### Code changes not reflected (Development)
```bash
# Ensure volume is mounted correctly
docker-compose config

# Restart services
docker-compose restart api
```

### High memory usage
```bash
# Check container stats
docker stats

# Adjust worker count in docker-compose.prod.yml
# Change: --workers 4 to --workers 2

# Set memory limits in docker-compose.prod.yml
```

### Health check failing
```bash
# Check health endpoint manually
docker-compose exec api curl http://localhost:8000/health

# View health check logs
docker inspect compliance_api --format='{{json .State.Health}}'
```

## Advanced Operations

### Shell Access
```bash
# Access container shell
docker-compose exec api bash

# Or using docker directly
docker exec -it compliance_api bash
```

### View Container Details
```bash
# Inspect container
docker inspect compliance_api

# View port mappings
docker port compliance_api
```

### Cleanup
```bash
# Remove all containers
docker-compose down

# Remove containers and volumes
docker-compose down -v

# Clean up Docker system
docker system prune -a
```

## Performance Tuning

### Worker Count
Adjust based on CPU cores:
```yaml
# Development: 1 worker (in docker-compose.yml)
command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Production: 2x CPU cores (in docker-compose.prod.yml)
command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Resource Limits
Modify in `docker-compose.prod.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Max CPU usage
      memory: 4G       # Max memory usage
    reservations:
      cpus: '1.0'      # Guaranteed CPU
      memory: 2G       # Guaranteed memory
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Build Docker image
  run: docker-compose -f docker-compose.prod.yml build

- name: Push to registry
  run: |
    docker tag compliance_api yourusername/compliance_api:latest
    docker push yourusername/compliance_api:latest
```

### Automated Deployment
```bash
# On your server
git pull origin main
docker-compose -f docker-compose.prod.yml up --build -d
```

## Best Practices

1. **Always use .env file** - Never commit API keys
2. **Monitor logs** - Check regularly for errors
3. **Test locally first** - Use docker-compose.yml before production
4. **Health checks** - Ensure endpoint returns 200 status
5. **Resource limits** - Prevent container from consuming all resources
6. **Regular updates** - Keep base image and dependencies updated
7. **Backup logs** - Persist logs outside container

## Monitoring

### Check Container Status
```powershell
docker-compose ps
```

### View Resource Usage
```powershell
docker stats compliance_api
```

### Export Logs
```powershell
docker-compose logs api > api_logs.txt
```

## Security Considerations

1. **Environment Variables**: Store sensitive data in `.env`, never in code
2. **Network Isolation**: Use Docker networks to isolate services
3. **Non-root User**: Consider running container as non-root (add to Dockerfile)
4. **Image Scanning**: Scan images for vulnerabilities before deployment
5. **Update Dependencies**: Keep base image and packages updated

## Support

For issues or questions:
- Check logs: `docker-compose logs -f api`
- Review health: `curl http://localhost:8000/health`
- Inspect container: `docker inspect compliance_api`
- Test locally: `docker-compose up` (without -d to see real-time output)
