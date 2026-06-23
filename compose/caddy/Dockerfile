# Custom Caddy image with the layer-4 (raw TCP) plugin.
#
# Why: this deployment terminates a valid (Let's Encrypt) cert on :9000 and then
# forwards the DECRYPTED stream to the remote MinIO at 10.0.0.2:9000 as raw TCP —
# NOT as HTTP. A normal HTTP reverse proxy (Go net/http) canonicalises response
# header names (x-amz-meta-* -> X-Amz-Meta-*), which breaks botocore/dtool-s3's
# case-sensitive S3 metadata parsing on dserver's server-side reads. A layer-4
# proxy never parses HTTP, so the lowercase headers survive. The plugin is not in
# the stock caddy:2-alpine image, so we build it in with xcaddy.
#
# Build is a Go compile — slow on a 1-vCPU/2-GB box. Build it on its own
# (`docker compose build caddy`) rather than alongside the webapp npm build.

FROM caddy:2-builder-alpine AS build
RUN xcaddy build --with github.com/mholt/caddy-l4

FROM caddy:2-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
