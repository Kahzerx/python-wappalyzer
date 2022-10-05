import json
import os.path
import re
import string

import requests

from wappalyzer.web_page import WebPage


class Wappalyzer:
    def __init__(self, technologies: dict):
        self.technologies = technologies
        self.confidence_regexp = re.compile(r"(.+)\\;confidence:(\d+)")

        for name, technology in list(self.technologies.items()):
            self._prepare_technology(technology)

    @classmethod
    def latest(cls):
        json_list = list(string.ascii_lowercase)
        json_list.append("_")

        if not os.path.isdir("data"):
            os.mkdir("data")

        if len(os.listdir("data")) == 0:
            for j in json_list:
                r = requests.get(f"https://raw.githubusercontent.com/wappalyzer/wappalyzer/master/src/technologies/{j}.json")
                with open(f"data/{j}.json", "w") as f:
                    f.write(r.text)

        technologies = {}
        for file in os.listdir("data"):
            if file.endswith(".json"):
                with open(f"data/{file}") as f:
                    loaded = json.loads(f.read())
                    technologies.update(loaded)

        return cls(technologies)

    def _prepare_technology(self, technology):
        # Ensure these keys' values are lists
        for key in ['url', 'html', 'scriptSrc', 'implies']:
            try:
                value = technology[key]
            except KeyError:
                technology[key] = []
            else:
                if not isinstance(value, list):
                    technology[key] = [value]

        # Ensure these keys exist
        for key in ['headers', 'meta']:
            try:
                _ = technology[key]
            except KeyError:
                technology[key] = {}

        # Ensure the 'meta' key is a dict
        obj = technology['meta']
        if not isinstance(obj, dict):
            technology['meta'] = {'generator': obj}

        # Ensure the 'meta' 'generator' is not an array
        obj = technology['meta']
        if 'generator' in obj and isinstance(obj['generator'], list):
            technology['meta']['generator'] = obj['generator'][0]

        for key in ['headers', 'meta']:
            obj = technology[key]
            technology[key] = {k.lower(): v for k, v in list(obj.items())}

        for key in ['url', 'html', 'scriptSrc']:
            technology[key] = [self._prepare_pattern(pattern) for pattern in technology[key]]

        for key in ['headers', 'meta']:
            obj = technology[key]
            for name, pattern in list(obj.items()):
                obj[name] = self._prepare_pattern(obj[name])

    @classmethod
    def _prepare_pattern(cls, pattern):
        """
        Strip out key:value pairs from the pattern and compile the regular
        expression.
        """
        attrs = {}
        pattern = pattern.split('\\;')
        for index, expression in enumerate(pattern):
            if index == 0:
                attrs['string'] = expression
                try:
                    attrs['regex'] = re.compile(expression, re.I)
                except re.error as err:
                    # warnings.warn(
                    #     "Caught '{error}' compiling regex: {regex}".format(
                    #         error=err, regex=pattern)
                    # )
                    # regex that never matches:
                    # http://stackoverflow.com/a/1845097/413622
                    attrs['regex'] = re.compile(r'(?!x)x')
            else:
                attr = expression.split(':')
                if len(attr) > 1:
                    key = attr.pop(0)
                    attrs[str(key)] = ':'.join(attr)
        return attrs

    def _has_technology(self, technology, webpage: WebPage):
        """
        Determine whether the web page matches the technology signature.
        """
        app = technology

        has_app = False
        # Search the easiest things first and save the full-text search of the
        # HTML for last

        for pattern in app['url']:
            if pattern['regex'].search(webpage.url):
                self._set_detected_app(app, 'url', pattern, webpage.url)

        for name, pattern in list(app['headers'].items()):
            if name in webpage.headers:
                content = webpage.headers[name]
                if pattern['regex'].search(content):
                    self._set_detected_app(app, 'headers', pattern, content, name)
                    has_app = True

        for pattern in technology['scriptSrc']:
            for script in webpage.scripts:
                if pattern['regex'].search(script):
                    self._set_detected_app(app, 'scriptSrc', pattern, script)
                    has_app = True

        for name, pattern in list(technology['meta'].items()):
            if name in webpage.meta:
                content = webpage.meta[name]
                if pattern['regex'].search(content):
                    self._set_detected_app(app, 'meta', pattern, content, name)
                    has_app = True

        for pattern in app['html']:
            if pattern['regex'].search(webpage.html):
                self._set_detected_app(app, 'html', pattern, webpage.html)
                has_app = True

        # Set total confidence
        if has_app:
            total = 0
            for index in app['confidence']:
                total += app['confidence'][index]
            app['confidenceTotal'] = total

        return has_app

    def _set_detected_app(self, app, app_type, pattern, value, key=''):
        """
        Store detected app.
        """
        app['detected'] = True

        # Set confidence level
        if key != '':
            key += ' '
        if 'confidence' not in app:
            app['confidence'] = {}
        if 'confidence' not in pattern:
            pattern['confidence'] = 100
        else:
            # Convert to int for easy adding later
            pattern['confidence'] = int(pattern['confidence'])
        app['confidence'][app_type + ' ' + key + pattern['string']] = pattern['confidence']

        # Dectect version number
        if 'version' in pattern:
            allmatches = re.findall(pattern['regex'], value)
            for i, matches in enumerate(allmatches):
                version = pattern['version']

                # Check for a string to avoid enumerating the string
                if isinstance(matches, str):
                    matches = [(matches)]
                for index, match in enumerate(matches):
                    # Parse ternary operator
                    ternary = re.search(re.compile('\\\\' + str(index + 1) + '\\?([^:]+):(.*)$', re.I), version)
                    if ternary and len(ternary.groups()) == 2 and ternary.group(1) is not None and ternary.group(2) is not None:
                        version = version.replace(ternary.group(0), ternary.group(1) if match != '' else ternary.group(2))

                    # Replace back references
                    version = version.replace('\\' + str(index + 1), match)
                if version != '':
                    if 'versions' not in app:
                        app['versions'] = [version]
                    elif version not in app['versions']:
                        app['versions'].append(version)
            self._set_app_version(app)

    def _set_app_version(self, app):
        """
        Resolve version number (find the longest version number that contains all shorter detected version numbers).
        """
        if 'versions' not in app:
            return

        app['versions'] = sorted(app['versions'], key=self._cmp_to_key(self._sort_app_versions))

    @classmethod
    def _sort_app_versions(cls, version_a, version_b):
        return len(version_a) - len(version_b)

    def _cmp_to_key(self, mycmp):
        """
        Convert a cmp= function into a key= function
        """

        # https://docs.python.org/3/howto/sorting.html
        class CmpToKey:
            def __init__(self, obj, *args):
                self.obj = obj

            def __lt__(self, other):
                return mycmp(self.obj, other.obj) < 0

            def __gt__(self, other):
                return mycmp(self.obj, other.obj) > 0

            def __eq__(self, other):
                return mycmp(self.obj, other.obj) == 0

            def __le__(self, other):
                return mycmp(self.obj, other.obj) <= 0

            def __ge__(self, other):
                return mycmp(self.obj, other.obj) >= 0

            def __ne__(self, other):
                return mycmp(self.obj, other.obj) != 0

        return CmpToKey

    def _get_implied_technologies(self, detected_technologies):
        """
        Get the set of technologies implied by `detected_technologies`.
        """
        def __get_implied_technologies(technologies):
            _implied_technologies = set()
            for tech in technologies:
                try:
                    for implie in self.technologies[tech]['implies']:
                        # If we have no doubts just add technology
                        if 'confidence' not in implie:
                            _implied_technologies.add(implie)

                        # Case when we have "confidence" (some doubts)
                        else:
                            try:
                                # Use more strict regexp (cause we have already checked the entry of "confidence")
                                # Also, better way to compile regexp one time, instead of every time
                                app_name, confidence = self.confidence_regexp.search(implie).groups()
                                if int(confidence) >= 50:
                                    _implied_technologies.add(app_name)
                            except (ValueError, AttributeError):
                                pass
                except KeyError:
                    pass
            return _implied_technologies

        implied_technologies = __get_implied_technologies(detected_technologies)
        all_implied_technologies = set()

        # Descend recursively until we've found all implied technologies
        while not all_implied_technologies.issuperset(implied_technologies):
            all_implied_technologies.update(implied_technologies)
            implied_technologies = __get_implied_technologies(all_implied_technologies)

        return all_implied_technologies

    def analyze(self, webpage: WebPage):
        detected_technologies = set()
        for tech_name, technology in list(self.technologies.items()):
            if self._has_technology(technology, webpage):
                detected_technologies.add(tech_name)

        detected_technologies |= self._get_implied_technologies(detected_technologies)

        return detected_technologies

    def analyze_with_versions(self, webpage: WebPage):
        detected_apps = self.analyze(webpage)
        versioned_apps = {}

        for app_name in detected_apps:
            versions = self.get_versions(app_name)
            versioned_apps[app_name] = {"versions": versions}

        return versioned_apps

    def get_versions(self, app_name):
        return [] if 'versions' not in self.technologies[app_name] else self.technologies[app_name]['versions']
