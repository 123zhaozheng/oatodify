import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['OPENAI_API_KEY'] = ''
os.environ['S3_ACCESS_KEY'] = ''
os.environ['S3_SECRET_KEY'] = ''

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from models import Base, OAFileInfo, BusinessCategory, ProcessingStatus
from config import settings


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(settings, 'cleanup_auto_delete', False)
    monkeypatch.setattr(settings, 'dify_dataset_id', 'kb-test')
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def make_doc(db):
    def create(file_id, **kwargs):
        data = dict(imagefileid=file_id, imagefilename=f'{file_id}.pdf',
                    business_category=BusinessCategory.PUBLIC_STANDARD,
                    processing_status=ProcessingStatus.COMPLETED, document_id=f'dify-{file_id}',
                    dify_dataset_id='kb-test', is_zw=True)
        data.update(kwargs)
        row = OAFileInfo(**data)
        db.add(row)
        db.commit()
        return row
    return create
