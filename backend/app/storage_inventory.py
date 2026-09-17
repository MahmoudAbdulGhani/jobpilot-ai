"""Read-only local inventory. No object-store calls and no file mutations."""
import hashlib
import json
import uuid
from pathlib import Path
from sqlalchemy import select, text
from app.core.db import SessionLocal
from app.core.config import get_settings
from app.models import Resume


def inventory(db, root):
    items = []
    ids = set()
    for identifier, expected_size in db.execute(select(Resume.id, Resume.size_bytes).order_by(Resume.id)):
        ids.add(str(identifier))
        path = root / str(identifier)
        if path.is_symlink():
            items.append({'id':str(identifier),'status':'symlink_refused'})
            continue
        try: data = path.read_bytes()
        except FileNotFoundError:
            items.append({'id':str(identifier),'status':'missing'})
            continue
        items.append({'id':str(identifier),'status':'ok' if len(data)==expected_size else 'size_mismatch',
                      'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                      'proposed_object_key':'resumes/'+str(identifier)})
    orphans = 0
    for path in root.iterdir() if root.is_dir() else []:
        try: uuid.UUID(path.name)
        except ValueError: continue
        if path.name not in ids: orphans += 1
    return {'dry_run':True,'provider_requests':0,'items':items,'unreferenced_local_files':orphans}


if __name__ == '__main__':
    with SessionLocal() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        print(json.dumps(inventory(db, Path(get_settings().RESUME_STORAGE_DIR)), indent=2))
