"""
تكامل اختياري مع GitHub: نسخ احتياطي + بلاغات
يتطلب: متغير بيئة GITHUB_TOKEN + مكتبة PyGithub
"""
import os


class GitHubBridge:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.g = None
        if self.token:
            try:
                from github import Github
                self.g = Github(self.token)
            except ImportError:
                self.g = None

    @property
    def available(self):
        return self.g is not None

    def whoami(self):
        if not self.available:
            return None
        try:
            return self.g.get_user().login
        except Exception:
            return None

    def backup_file(self, file_path, filename, description="JARVIS backup"):
        """يحفظ ملفاً كـ Gist خاص"""
        if not self.available:
            return None
        try:
            from github.InputFileContent import InputFileContent
            content = open(file_path, "rb").read().decode("latin-1")
            gist = self.g.get_user().create_gist(
                False, {filename: InputFileContent(content)}, description)
            return gist.html_url
        except Exception:
            return None

    def create_issue(self, repo_full_name, title, body):
        if not self.available:
            return None
        try:
            repo = self.g.get_repo(repo_full_name)
            return repo.create_issue(title=title, body=body).html_url
        except Exception:
            return None
