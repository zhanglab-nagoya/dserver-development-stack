// vue.config.js — bind-mounted over the webapp container's /app/vue.config.js for the
// HTTPS deployment (see docker-compose.override.yml). Avoids editing the
// dtool-lookup-webapp submodule. Mirrors the submodule's own config and adds the
// devServer tweak needed when the dev server runs behind Caddy on a different hostname.
const { defineConfig } = require("@vue/cli-service");

module.exports = defineConfig({
  transpileDependencies: true,
  // Disable ESLint during development/build to avoid eslint 9.x incompatibility
  // with @vue/cli-plugin-eslint (which passes deprecated 'extensions' option).
  lintOnSave: false,
  devServer: {
    // webpack-dev-server (vue-cli 5) rejects requests whose Host header isn't in its
    // allow-list. Behind Caddy the Host is the public FQDN, so accept all hosts.
    allowedHosts: "all",
    client: {
      // Behind the Caddy TLS proxy the HMR client must use wss:// via the page's own
      // host (Caddy proxies /ws -> webapp:8080 and upgrades the socket). Without this it
      // defaults to ws://<container-ip>:8080/ws, which the browser blocks as insecure on
      // an https page. The 0.0.0.0:0 sentinels mean "infer host+port from the browser".
      webSocketURL: "auto://0.0.0.0:0/ws",
    },
  },
});
