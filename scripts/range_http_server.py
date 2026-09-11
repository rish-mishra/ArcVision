"""
Static file server WITH HTTP Range support, for QA use only.

`python -m http.server` ignores Range headers entirely (always returns a
full 200 response), which makes it unsuitable for testing video seeking --
Chromium reports `video.seekable` as only `[0, 0]` against a server that
can't serve partial content, so every Jump-to-Shot click silently fails to
seek. Any real static host used for actual publication (GitHub Pages,
Netlify, S3, nginx, etc.) supports Range requests correctly, so this
server exists purely so local QA reflects real-world playback behavior.
Not part of the shipped app or the exported dist/ bundle.

Usage:
    .venv\\Scripts\\python scripts\\range_http_server.py <directory> <port>
"""
import http.server
import os
import re
import socketserver
import sys


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        if not os.path.exists(path):
            self.send_error(404, "File not found")
            return None

        file_size = os.path.getsize(path)
        range_header = self.headers.get("Range")
        if not range_header:
            self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Type", self.guess_type(path))
            self.end_headers()
            return open(path, "rb")

        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if not m:
            self.send_error(416, "Invalid Range header")
            return None
        start_s, end_s = m.groups()
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return None

        length = end - start + 1
        self.send_response(206)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Type", self.guess_type(path))
        self.end_headers()

        f = open(path, "rb")
        f.seek(start)
        self._range_remaining = length
        self._range_source = f
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        chunk_size = 64 * 1024
        while remaining > 0:
            chunk = source.read(min(chunk_size, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8843
    os.chdir(directory)
    with socketserver.TCPServer(("", port), RangeRequestHandler) as httpd:
        print(f"Serving {directory} at http://localhost:{port} (Range-request capable)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
