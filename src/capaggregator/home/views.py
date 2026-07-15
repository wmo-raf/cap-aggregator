from django.conf import settings
from django.views.generic import TemplateView


class ExplorerView(TemplateView):
    """Shell for the explorer SPA.

    Serves every path under /explorer/ so vue-router (history mode) owns the
    map/table/authorities/notify sub-routes and deep links survive full page
    loads. The bundle is resolved by django-vite: the Vite dev server in
    dev_mode, hashed assets from the built manifest otherwise.
    """

    template_name = "capagg_home/explorer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Rendered as a json_script the SPA reads at boot (frontend/src/lib/config.ts)
        context["capagg_config"] = {"tilesBase": settings.CAPAGG_TILES_BASE}
        return context


explorer = ExplorerView.as_view()
