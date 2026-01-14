from cement.core import handler, controller
from dscan.plugins import BasePlugin
from dscan.common.update_api import GitRepo
import dscan.common.update_api as ua
import dscan.common.versions
import re

class Drupal(BasePlugin):

    plugins_base_url = [
            "%ssites/all/modules/%s/",
            "%ssites/default/modules/%s/",
            "%smodules/contrib/%s/",
            "%smodules/%s/"]
    themes_base_url = [
            "%ssites/all/themes/%s/",
            "%ssites/default/themes/%s/",
            "%sthemes/%s/"]

    forbidden_url = "sites/"
    regular_file_url = ["misc/drupal.js", 'core/misc/drupal.js']
    module_common_file = "LICENSE.txt"
    update_majors = ['6','7','8', '9', '10', '11']

    interesting_urls = [
            ("CHANGELOG.txt", "Default changelog file"),
            ("user/login", "Default admin"),
        ]

    interesting_module_urls = [
        ('CHANGELOG.txt', 'Changelog file'),
        ('CHANGELOG.md', 'Changelog file'),
        ('changelog.txt', 'Changelog file'),
        ('CHANGELOG.TXT', 'Changelog file'),
        ('README.txt', 'README file'),
        ('README.md', 'README file'),
        ('readme.txt', 'README file'),
        ('README.TXT', 'README file'),
        ('LICENSE.txt', 'License file'),
        ('API.txt', 'Contains API documentation for the module')
    ]

    class Meta:
        label = 'drupal'

    @controller.expose(help='drupal related scanning tools')
    def drupal(self):
        self.plugin_init()

    def update_version_check(self):
        """
        @return: True if new tags have been made in the github repository.
        """
        return ua.github_tags_newer('drupal/drupal/', self.versions_file,
                update_majors=self.update_majors)

    def update_version(self):
        """
        @return: updated VersionsFile
        """
        gr, versions_file, new_tags = ua.github_repo_new('drupal/drupal/',
                'drupal/drupal', self.versions_file, self.update_majors)

        hashes = {}
        for version in new_tags:
            gr.tag_checkout(version)
            hashes[version] = gr.hashes_get(versions_file)

        versions_file.update(hashes)
        return versions_file

    def update_plugins_check(self):
        return ua.update_modules_check(self)

    def update_plugins(self):
        """
        @return: (plugins, themes) a tuple which contains two list of
            strings, the plugins and the themes.
        """
        plugins_url = 'https://drupal.org/project/project_module?page=%s'
        plugins_css = '.node-project-module > h2 > a'
        themes_url = 'https://drupal.org/project/project_theme?page=%s'
        themes_css = '.node-project-theme > h2 > a'
        per_page = 25

        plugins = []
        for elem in ua.modules_get(plugins_url, per_page, plugins_css):
            plugins.append(elem['href'].split("/")[-1])

        themes = []
        for elem in ua.modules_get(themes_url, per_page, themes_css):
            themes.append(elem['href'].split("/")[-1])

        return plugins, themes

    def enumerate_version_from_html(self, url, timeout=15, headers={}):
        """
        Extract exact version from HTML query parameters in asset URLs.
        Drupal 8+ adds ?v=X.Y.Z to JS/CSS URLs for cache busting.
        This is more accurate than MD5 fingerprinting for patch versions.

        @param url: the base URL to check
        @param timeout: request timeout in seconds
        @param headers: headers to pass to requests.get()
        @return: version string (e.g., "11.2.10") or None if not found
        """
        try:
            response = self.session.get(url, timeout=timeout, headers=headers, verify=False)

            # Try to parse HTML even with non-200 status codes (some sites may return content)
            if response.status_code in [200, 403]:
                # Pattern matches: /core/misc/drupal.js?v=11.2.10 or similar
                # Looks for ?v= followed by semantic version (X.Y.Z)
                pattern = r'\?v=(\d+\.\d+\.\d+)'
                match = re.search(pattern, response.text)

                if match:
                    return match.group(1)

        except Exception:
            # Silently fail and let fingerprinting handle it
            pass

        return None

    def enumerate_version(self, url, threads=10, verb='head',
            timeout=15, hide_progressbar=False, headers={}):
        """
        Override parent method to try HTML parsing first, then fall back to fingerprinting.

        @param url: the url to check
        @param threads: number of threads for fingerprinting
        @param verb: HTTP verb to use
        @param timeout: request timeout in seconds
        @param hide_progressbar: whether to hide progress bar
        @param headers: headers to pass to requests
        @return: (possible_versions, is_empty)
        """
        # Try to get exact version from HTML query parameters first
        html_version = self.enumerate_version_from_html(url, timeout, headers)

        # Always do fingerprinting for verification
        fingerprint_versions, is_empty = super(Drupal, self).enumerate_version(
            url, threads, verb, timeout, hide_progressbar, headers
        )

        if html_version:
            # If we found a version in HTML, check if it's consistent with fingerprinting
            if not fingerprint_versions or html_version in fingerprint_versions:
                # HTML version is consistent, use it as the definitive answer
                self.html_version_found = html_version
                return [html_version], False
            else:
                # HTML version conflicts with fingerprinting - trust fingerprinting
                # but store the HTML version for informational purposes
                self.html_version_found = html_version
                return fingerprint_versions, is_empty

        # No HTML version found, use fingerprinting results
        self.html_version_found = None
        return fingerprint_versions, is_empty

def load(app=None):
    handler.register(Drupal)

