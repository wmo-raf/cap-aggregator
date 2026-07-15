"""Explorer SPA shell: every path under /explorer/ serves the same shell so
vue-router (history mode) owns the sub-routes and deep links survive reloads."""

from django.test import TestCase


class ExplorerShellTests(TestCase):
    SHELL_MARKER = 'id="capagg-explorer"'

    def test_explorer_root_serves_shell(self):
        response = self.client.get("/explorer/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.SHELL_MARKER)

    def test_all_menu_routes_serve_shell(self):
        for path in ("/explorer/map", "/explorer/table", "/explorer/authorities", "/explorer/notify"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.SHELL_MARKER)

    def test_unknown_subroute_serves_shell_for_client_side_handling(self):
        response = self.client.get("/explorer/some/future/route")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.SHELL_MARKER)

    def test_bare_explorer_redirects_to_slash(self):
        response = self.client.get("/explorer")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], "/explorer/")

    def test_shell_loads_the_vite_entry(self):
        response = self.client.get("/explorer/")

        # dev_mode → dev-server module URL; prod → hashed asset from the
        # manifest. Either way the entry module must be referenced.
        self.assertContains(response, "src/main.ts" if self._dev_mode() else "assets/main-")

    @staticmethod
    def _dev_mode():
        from django.conf import settings

        return settings.DJANGO_VITE["default"]["dev_mode"]

    def test_shell_injects_runtime_config_with_tiles_base(self):
        """The SPA reads the Martin base URL from a json_script config block."""
        import json

        from django.conf import settings

        response = self.client.get("/explorer/")

        self.assertContains(response, 'id="capagg-config"')
        content = response.content.decode()
        start = content.index('id="capagg-config"')
        payload = content[content.index(">", start) + 1 : content.index("</script>", start)]
        self.assertEqual(json.loads(payload)["tilesBase"], settings.CAPAGG_TILES_BASE)
