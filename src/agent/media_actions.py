"""
Neura Media Actions
بحث مقاطع YouTube - قراءة فقط، آمن تماماً، لا يحتاج Safety Gate.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yt_dlp import YoutubeDL


def _fmt_duration(seconds):
    if not seconds:
        return '--:--'
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return '%d:%02d:%02d' % (h, m, s)
    return '%d:%02d' % (m, s)


def _fmt_views(views):
    if not views:
        return '؟'
    if views >= 1000000:
        return '%.1fM' % (views / 1000000.0)
    if views >= 1000:
        return '%.1fK' % (views / 1000.0)
    return str(views)


def search_videos(query, count=5):
    """يبحث في YouTube ويرجع قائمة نتائج (قراءة فقط)."""
    print('🔍 بحث YouTube: "%s" (أفضل %d نتائج)' % (query, count))
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': True,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info('ytsearch%d:%s' % (count, query), download=False)

    results = []
    for e in (info.get('entries') or []):
        results.append({
            'id': e.get('id'),
            'title': e.get('title'),
            'channel': e.get('channel') or e.get('uploader') or '؟',
            'duration': _fmt_duration(e.get('duration')),
            'views': _fmt_views(e.get('view_count')),
            'url': 'https://www.youtube.com/watch?v=%s' % e.get('id'),
        })
    return results


def print_results(results):
    print()
    print('=' * 60)
    print('📹 النتائج (%d):' % len(results))
    print('=' * 60)
    for i, r in enumerate(results, 1):
        print('%d. %s' % (i, r['title']))
        print('   👤 %s | ⏱️ %s | 👁️ %s' % (r['channel'], r['duration'], r['views']))
        print('   🔗 %s' % r['url'])
        print()


if __name__ == '__main__':
    print('Neura Media Actions - Demo (قراءة فقط، آمن تماماً)')
    print('=' * 60)
    results = search_videos('llama.cpp Vulkan AMD GPU benchmark', count=5)
    print_results(results)
