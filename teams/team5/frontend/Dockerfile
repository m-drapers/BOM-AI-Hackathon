FROM node:18-alpine

# Install pnpm
RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app

# Copy dependency files first for layer caching
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy application source
COPY . .

# Build the Next.js application
RUN pnpm build

# Expose port
EXPOSE 3000

# Run the production server
CMD ["pnpm", "start"]
