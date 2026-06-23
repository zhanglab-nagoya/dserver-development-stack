# dtool-lookup-webapp Docker image
# Node.js based container for Vue.js development server
FROM node:20-alpine

# Copy and build dserver-client-js first.
# Its package.json defines a `prepare` script that runs the build (tsup) during
# `npm install`, so the full source must be present before installing — copying
# only package*.json first makes `prepare` fail with "Cannot find src/index.ts".
# (--ignore-scripts is not an option: tsup needs esbuild's install postinstall.)
WORKDIR /dserver-client-js
COPY ./dserver-client-js/ ./
RUN npm install

# Set working directory for webapp
WORKDIR /app

# Copy only package.json and fix the local dependency path
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/package.json ./
RUN sed -i 's|file:../../dserver-client-js|file:/dserver-client-js|g' package.json

# Install dependencies (generates fresh lockfile).
# --ignore-scripts: prevents the symlinked file: dep dserver-client from running
# its "prepare" hook (tsup --clean), which would wipe the dist/ built just above.
# The webapp itself defines no install lifecycle scripts, so nothing is lost.
RUN --mount=type=cache,target=/root/.npm npm install --ignore-scripts

# Copy source files only (exclude node_modules, package-lock.json which would override)
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/src ./src
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/public ./public
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/tsconfig*.json ./
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/babel.config.js ./
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/vue.config.js ./
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/.eslintrc.js ./
COPY ./dtool-lookup-webapp/dtool-lookup-webapp/.browserslistrc ./

# Create .env file for Vue CLI
# Environment variables starting with VUE_APP_ are passed at runtime
# but we need a placeholder .env for the build process
RUN echo 'VUE_APP_DTOOL_LOOKUP_SERVER_URL=http://localhost:5000' > .env && \
    echo 'VUE_APP_DTOOL_LOOKUP_SERVER_TOKEN_GENERATOR_URL=http://localhost:5001/token' >> .env

# Expose the development server port
EXPOSE 8080

# Default command runs the development server
CMD ["npm", "run", "serve", "--", "--host", "0.0.0.0"]
