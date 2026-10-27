"""
File Extractor - extract code files from model responses
Parses fenced code blocks: ```language filename\n code ```
"""
import logging
import re
from pathlib import Path
from typing import List

from .invoice_schema import ProjectFile

logger = logging.getLogger(__name__)

# Known programming languages (to strip from filename)
LANG_PREFIXES = [
    "python", "py", "javascript", "js", "typescript", "ts",
    "html", "css", "json", "yaml", "yml", "toml", "xml",
    "cpp", "c", "h", "hpp", "java", "kotlin", "kt",
    "rust", "rs", "go", "golang", "ruby", "rb",
    "bash", "sh", "zsh", "fish", "powershell", "ps1",
    "sql", "graphql", "r", "matlab", "julia",
    "lua", "perl", "php", "swift", "scala", "dart",
    "jsx", "tsx", "vue", "svelte", "astro",
    "markdown", "md", "plaintext", "text", "txt",
]

# Known file extensions
KNOWN_EXTENSIONS = {
    "py", "js", "ts", "jsx", "tsx", "html", "css", "json",
    "yaml", "yml", "toml", "xml", "md", "txt", "sh", "bash",
    "c", "cpp", "h", "hpp", "java", "kt", "rs", "go", "rb",
    "php", "swift", "scala", "dart", "lua", "r", "sql",
    "vue", "svelte", "astro", "ini", "cfg", "conf",
}


def _clean_filename(token: str) -> str:
    """Clean a filename token: remove dangerous chars and path traversal."""
    if not token:
        return ""
    
    # Remove backticks and other dangerous chars
    token = token.replace("`", "")
    token = token.replace("*", "")
    token = token.replace(":", "")
    token = token.replace("?", "")
    token = token.replace("<", "")
    token = token.replace(">", "")
    token = token.replace("|", "")
    token = token.replace('"', "")
    token = token.replace("'", "")
    
    # Remove path components (no directory traversal)
    token = token.replace("\\", "/")
    if "/" in token:
        token = token.rsplit("/", 1)[-1]
    
    return token.strip()


def _strip_language_prefix(filename: str) -> str:
    """Strip language name if accidentally included in filename.
    
    Examples:
        "python snake_game.py" -> "snake_game.py"
        "javascript app.js" -> "app.js"
        "snake_game.py" -> "snake_game.py" (unchanged)
    """
    lower = filename.lower()
    
    for lang in LANG_PREFIXES:
        # Check if filename starts with "lang " or "lang_"
        for sep in (" ", "_", "-"):
            prefix = lang + sep
            if lower.startswith(prefix):
                return filename[len(prefix):].strip()
        
        # Check if filename starts with just the lang name (no extension yet)
        if lower == lang:
            # Filename is just the language name - skip it
            return ""
    
    return filename


def _looks_like_filename(token: str) -> bool:
    """Check if a token looks like a valid filename."""
    if not token or len(token) > 100:
        return False
    
    # Must contain a dot (extension)
    if "." not in token:
        return False
    
    # Check if extension is known
    ext = token.rsplit(".", 1)[-1].lower()
    if ext not in KNOWN_EXTENSIONS:
        return False
    
    # Should not contain spaces (after cleaning)
    if " " in token:
        return False
    
    return True


class FileExtractor:
    """Extracts code files from model responses."""
    
    @staticmethod
    def extract_files(response: str) -> List[ProjectFile]:
        """
        Extract code blocks from model response.
        
        Supports these formats:
        1. ```language filename\n code ```
        2. filename\n ```language\n code ```
        3. ```language\n code ``` (auto-named file_1.py, file_2.py, etc.)
        """
        files = []
        seen_names = set()  # Track names to avoid duplicates
        
        # Pattern: ```language [optional filename]\n code ```
        # Using re.DOTALL to match across lines
        pattern = r'```(\w+)(?:[ \t]+([^\n]+))?\s*\n([\s\S]*?)```'
        matches = re.finditer(pattern, response, re.MULTILINE)
        
        for match in matches:
            lang = match.group(1).strip().lower()
            raw_filename = match.group(2)  # May be None
            code = match.group(3).strip()
            
            # Skip empty code blocks
            if len(code) < 20:
                continue
            
            # Process filename
            filename = None
            if raw_filename:
                # Clean the filename
                filename = _clean_filename(raw_filename)
                
                # Strip language prefix if present
                filename = _strip_language_prefix(filename)
                
                # Check if it looks like a filename
                if filename and _looks_like_filename(filename):
                    # Good filename
                    pass
                elif filename:
                    # Doesn't look like a filename - maybe it's a description
                    filename = None
            
            # If no filename from code block, try to get from previous line
            if not filename:
                # Look at the line before the code block
                match_start = match.start()
                before = response[:match_start]
                last_line = before.rstrip().split("\n")[-1].strip()
                
                if last_line:
                    cleaned = _clean_filename(last_line)
                    if _looks_like_filename(cleaned):
                        filename = cleaned
            
            # Auto-generate filename if still none
            if not filename:
                ext = _lang_to_extension(lang)
                # Generate unique name
                base_name = f"file_{len(files) + 1}"
                filename = f"{base_name}.{ext}"
            
            # Ensure uniqueness
            base_filename = filename
            counter = 1
            while filename in seen_names:
                name_part = base_filename.rsplit(".", 1)[0]
                ext_part = base_filename.rsplit(".", 1)[1] if "." in base_filename else "txt"
                filename = f"{name_part}_{counter}.{ext_part}"
                counter += 1
            
            seen_names.add(filename)
            
            # Create the ProjectFile
            project_file = ProjectFile(
                name=filename,
                language=lang,
                content=code,
            )
            
            # Replace existing file with same name, or append
            replaced = False
            for i, existing in enumerate(files):
                if existing.name == filename:
                    files[i] = project_file
                    replaced = True
                    break
            
            if not replaced:
                files.append(project_file)
        
        # Log what we found
        if files:
            logger.info(f"   Extracted {len(files)} file(s):")
            for f in files:
                logger.info(f"      - {f.name} ({f.language}, {f.size_bytes} bytes)")
        else:
            logger.warning("   No code files found in response")
        
        return files
    
    @staticmethod
    def save_files(files: List[ProjectFile], project_dir: Path) -> List[Path]:
        """Save extracted files to disk."""
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        saved_paths = []
        
        for f in files:
            # Validate filename one more time
            name = _clean_filename(f.name)
            if not name or name in (".", "..") or "/" in name or "\\" in name:
                logger.warning(f"   Skipping unsafe filename: {f.name}")
                continue
            
            filepath = project_dir / name
            try:
                filepath.write_text(f.content, encoding="utf-8")
                saved_paths.append(filepath)
                logger.info(f"   💾 Saved: {filepath.name} ({f.size_bytes} bytes)")
            except OSError as e:
                logger.error(f"   Failed to save {name}: {e}")
        
        return saved_paths


def _lang_to_extension(lang: str) -> str:
    """Convert language name to file extension."""
    mapping = {
        "python": "py",
        "py": "py",
        "javascript": "js",
        "js": "js",
        "typescript": "ts",
        "ts": "ts",
        "html": "html",
        "css": "css",
        "json": "json",
        "yaml": "yaml",
        "yml": "yml",
        "toml": "toml",
        "xml": "xml",
        "cpp": "cpp",
        "c": "c",
        "h": "h",
        "hpp": "hpp",
        "java": "java",
        "kotlin": "kt",
        "rust": "rs",
        "rs": "rs",
        "go": "go",
        "ruby": "rb",
        "rb": "rb",
        "bash": "sh",
        "sh": "sh",
        "sql": "sql",
        "markdown": "md",
        "md": "md",
        "jsx": "jsx",
        "tsx": "tsx",
        "vue": "vue",
        "svelte": "svelte",
        "dart": "dart",
        "swift": "swift",
        "scala": "scala",
        "r": "r",
        "lua": "lua",
        "php": "php",
        "perl": "pl",
    }
    return mapping.get(lang.lower(), "txt")
