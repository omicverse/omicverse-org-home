const DOCS_URL = "https://omicverse.readthedocs.io/";
const DOCS_PATHS = new Set(["/learn", "/learn/", "/learn.html"]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (DOCS_PATHS.has(url.pathname)) {
      return Response.redirect(DOCS_URL, 302);
    }

    return env.ASSETS.fetch(request);
  },
};
