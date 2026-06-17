from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class ManifestStaticFilesStorageWithJsModules(ManifestStaticFilesStorage):
    """Manifest storage with hashed ES module import paths rewritten on collectstatic."""

    support_js_module_import_aggregation = True
