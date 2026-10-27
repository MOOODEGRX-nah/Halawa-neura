"""Small, explicit tools. Shell, application launching and sending mail are disabled."""
from pydantic import BaseModel, ConfigDict, Field


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=3, ge=1, le=5)


class DraftArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    to_address: str = Field(min_length=3, max_length=320, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    subject: str = Field(max_length=300)
    body: str = Field(max_length=20_000)


class SafeActions:
    allowed_apps = {'linux': [], 'windows': []}

    def __init__(self, search_provider=None):
        self.search_provider = search_provider

    def launch_app(self, app_name):
        return {'status': 'blocked', 'reason': 'Application execution is disabled'}

    def search_web(self, query, max_results=3):
        args = SearchArgs(query=query, max_results=max_results)
        provider = self.search_provider
        if provider is None:
            try:
                from ddgs import DDGS
                provider = DDGS(timeout=10).text
            except ImportError:
                return {'status': 'unavailable', 'reason': 'Install optional ddgs dependency'}
        try:
            records = list(provider(args.query, max_results=args.max_results))[:args.max_results]
            return {'status': 'success', 'results': [{'title': r.get('title', ''), 'snippet': r.get('body', ''),
                                                     'url': r.get('href', '')} for r in records]}
        except Exception as exc:
            return {'status': 'error', 'reason': f'Search failed: {exc}'}

    def draft_email(self, to_address, subject, body):
        args = DraftArgs(to_address=to_address, subject=subject, body=body)
        return {'status': 'drafted', 'draft': args.model_dump(),
                'message': 'Draft only. Sending email is not implemented.'}

    def dispatch(self, tool, args):
        if tool == 'search_web':
            validated = SearchArgs.model_validate(args)
            return self.search_web(**validated.model_dump())
        if tool == 'draft_email':
            validated = DraftArgs.model_validate(args)
            return self.draft_email(**validated.model_dump())
        return {'status': 'unavailable', 'reason': f'Tool {tool} is not implemented or enabled'}

    @staticmethod
    def capabilities():
        return [{'id': 'search_web', 'permissions': ['network:search'], 'requires_approval': False},
                {'id': 'draft_email', 'permissions': [], 'requires_approval': False}]
