# Reuse the same base image as your main api/worker services.
# All Python deps are already installed there.
FROM orqestra-api:latest

# Working directory matches the rest of the stack
WORKDIR /app

# No copy needed — demo/ is bind-mounted via docker-compose volumes