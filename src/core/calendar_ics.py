"""N084: calendar exchange through standard iCalendar files — no account, no network, no side effects.

Export: pending reminders become VEVENTs with a display alarm; each UID is the reminder id, so
importing the file again into a calendar app updates the same events instead of duplicating them.
Import: future, timed VEVENTs from a file the user picked become reminders; the event UID is the
idempotency key, so importing the same file twice creates nothing new. Recurrence rules are not
expanded (reported as skipped) rather than guessed.
"""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_EVENTS = 200


class CalendarError(ValueError):
    pass


def _escape(text):
    return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _unescape(text):
    return re.sub(r'\\([\\;,nN])', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), text)


def _fold(line):
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, current = [], ''
    for char in line:
        if len((current + char).encode()) > 74:
            parts.append(current)
            current = char
        else:
            current += char
    parts.append(current)
    return '\r\n '.join(parts)


def _stamp(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def export_reminders(reminders, now):
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Neura AI//Reminders//AR', 'CALSCALE:GREGORIAN', 'X-WR-CALNAME:تذكيرات Neura']
    for reminder in reminders:
        lines += ['BEGIN:VEVENT', 'UID:' + reminder['id'] + '@neura.local', 'DTSTAMP:' + _stamp(now),
                  'DTSTART:' + _stamp(reminder['due']), 'DTEND:' + _stamp(reminder['due'] + 900),
                  'SUMMARY:' + _escape(reminder['text']), 'BEGIN:VALARM', 'ACTION:DISPLAY',
                  'DESCRIPTION:' + _escape(reminder['text']), 'TRIGGER:PT0S', 'END:VALARM', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'


def _parse_time(value, params, default_zone):
    value = value.strip()
    if re.fullmatch(r'\d{8}', value):
        return None  # all-day events have no reminder time; reported as skipped
    match = re.fullmatch(r'(\d{8}T\d{6})(Z?)', value)
    if not match:
        raise CalendarError('صيغة وقت غير مفهومة: ' + value[:40])
    moment = datetime.strptime(match.group(1), '%Y%m%dT%H%M%S')
    if match.group(2):
        return moment.replace(tzinfo=timezone.utc).timestamp()
    zone = re.search(r'TZID=([^;:]+)', params or '')
    try:
        tz = ZoneInfo(zone.group(1).strip('"')) if zone else ZoneInfo(default_zone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(default_zone)
    return moment.replace(tzinfo=tz).timestamp()


def parse_events(text, default_zone='Asia/Riyadh'):
    if len(text) > 2_000_000 or 'BEGIN:VCALENDAR' not in text:
        raise CalendarError('الملف ليس تقويم iCalendar (.ics) صالحًا.')
    unfolded = re.sub(r'\r?\n[ \t]', '', text)
    events, skipped = [], {'all_day': 0, 'recurring': 0, 'invalid': 0}
    for block in re.findall(r'BEGIN:VEVENT\r?\n(.*?)END:VEVENT', unfolded, re.S)[:MAX_EVENTS]:
        fields = {}
        for line in block.splitlines():
            match = re.match(r'([A-Z-]+)((?:;[^:]*)?):(.*)', line)
            if match and match.group(1) not in fields:
                fields[match.group(1)] = (match.group(2), match.group(3))
        if 'RRULE' in fields:
            skipped['recurring'] += 1
            continue
        try:
            start = _parse_time(fields['DTSTART'][1], fields['DTSTART'][0], default_zone) if 'DTSTART' in fields else None
        except CalendarError:
            skipped['invalid'] += 1
            continue
        if start is None:
            skipped['all_day' if 'DTSTART' in fields else 'invalid'] += 1
            continue
        summary = _unescape(fields.get('SUMMARY', ('', ''))[1]).strip() or 'موعد'
        uid = fields.get('UID', ('', ''))[1].strip() or summary + '@' + str(int(start))
        events.append({'uid': uid[:200], 'summary': summary[:300], 'start': start})
    return events, skipped


def import_events(store, text, timezone_name, now):
    events, skipped = parse_events(text, timezone_name)
    created, existing, past = [], 0, 0
    for event in events:
        if event['start'] <= now:
            past += 1
            continue
        key = 'ics:' + event['uid']
        before = store.db.execute('SELECT 1 FROM reminders WHERE request_id=?', (key,)).fetchone()
        reminder = store.add_reminder(event['summary'], event['start'], timezone_name, 'calendar', key)
        if before:
            existing += 1
        else:
            created.append(reminder)
    return {'created': created, 'already_imported': existing, 'past': past, 'skipped': skipped}
