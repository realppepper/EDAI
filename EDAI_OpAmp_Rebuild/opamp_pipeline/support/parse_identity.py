"""Provenance checks shared by layout validation and graph collection."""
import hashlib
from pathlib import Path


def parse_image_issues(parsed, image, source_hash, verify_bytes=True):
    issues=[]
    if parsed.get('source_sha256')!=source_hash or parsed.get('pdf_page')!=image['pdf_page']:
        issues.append('Parse PDF/page identity mismatch')
    if parsed.get('image_sha256')!=image['image_sha256']:
        issues.append('Parse and current rendered image hashes differ')
    if sorted(parsed.get('roles',[]))!=sorted(image.get('roles',[])):
        issues.append('Parse page roles differ from current render manifest')
    if verify_bytes:
        path=Path(image['image_path'])
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=image['image_sha256']:
            issues.append('Current rendered image bytes differ from manifest')
    return issues
