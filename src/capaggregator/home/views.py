from django.views.generic import TemplateView


class ExplorerView(TemplateView):
    """Shell for the explorer SPA.

    Serves every path under /explorer/ so vue-router (history mode) owns the
    map/table/authorities/notify sub-routes and deep links survive full page
    loads. The bundle is resolved by django-vite: the Vite dev server in
    dev_mode, hashed assets from the built manifest otherwise.
    """

    template_name = "capagg_home/explorer.html"


explorer = ExplorerView.as_view()
