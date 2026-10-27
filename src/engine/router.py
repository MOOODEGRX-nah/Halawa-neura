"""One deterministic selection policy for API, Telegram and task handoffs."""
import re


class Router:
    def __init__(self, residency_manager):
        self.residency = residency_manager
        self.intent_rules = [
            (r'ابحث عن|search for|ما هي اخبار', 'tool_search'),
            (r'ارسل ايميل|أرسل.*بريد|send email|اكتب رسالة لـ', 'tool_email'),
            (r'\b(code|function|class|debug|error|refactor|script|game|app|python|javascript|html|css)\b|برمج|كود|دالة|لعبة|تطبيق|اكتب.*برنامج', 'coder'),
            (r'\b(image|vision)\b|صورة|اقرأ هذه الصورة', 'vision'),
            (r'\b(math|solve|prove|calculate|deep analysis|comprehensive)\b|رياضيات|برهان|احسب|استنتج|تحليل شامل|تقرير طويل|اكتب بحث', 'expert'),
        ]

    def detect_intent(self, user_input, has_image=False):
        if has_image:
            return 'vision'
        return next((intent for pattern, intent in self.intent_rules
                     if re.search(pattern, user_input, re.I)), 'daily')

    def get_model_id_for_tier(self, tier_name):
        tier = self.residency.tiers.get(tier_name.lower())
        if not tier:
            raise ValueError(f'Unknown tier: {tier_name}')
        return tier['model_id']

    def route(self, user_input: str, has_image: bool = False, context_length: int = 4096,
              requested_tier=None, requested_model=None) -> tuple[str, str, str, str]:
        intent = self.detect_intent(user_input, has_image)
        requested_tier = requested_tier.lower() if requested_tier else None
        tier = requested_tier or ('daily' if intent.startswith('tool_') else intent)
        if has_image and requested_tier not in (None, 'vision'):
            raise ValueError('Image messages require the VISION tier')
        if requested_model:
            candidates = [name for name, info in self.residency.tiers.items() if info['model_id'] == requested_model]
            if not candidates:
                raise ValueError('Model is not assigned to an active tier')
            if requested_tier and self.get_model_id_for_tier(tier) != requested_model:
                raise ValueError('Conflicting model and tier')
            tier = tier if tier in candidates else candidates[0]
            if has_image and tier != 'vision':
                raise ValueError('Image messages require a vision model')
        model_id = self.get_model_id_for_tier(tier)
        allowed, note = self.residency.can_load(model_id, context_length, tier=tier)
        reason = f'Intent: {intent}; tier: {tier}; {note}'
        if not allowed and not requested_tier and not requested_model and tier in ('coder', 'expert'):
            candidate = self.get_model_id_for_tier('daily')
            ok, fallback_note = self.residency.can_load(candidate, context_length, tier='daily')
            if ok:
                tier, model_id = 'daily', candidate
                reason = f'Fallback to DAILY: {note}; {fallback_note}'
        return tier, model_id, reason, intent
