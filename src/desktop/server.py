"""Private child process of the native desktop; no terminal interaction."""
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run('src.backend.api:app', host='127.0.0.1', port=args.port,
                workers=1, proxy_headers=False, log_level='warning')
