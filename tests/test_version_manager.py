"""
测试文档版本管理和有效期管理功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.version_manager import version_manager
from database import get_db_session
from models import OAFileInfo, ProcessingStatus, BusinessCategory
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_extract_title():
    """测试从文档名提取标题"""
    print("\n=== 测试提取标题功能 ===")

    test_cases = [
        "关于印发《信贷管理办法》的通知.docx",
        "《客户服务规范》修订版.pdf",
        "通知：关于废除《旧制度》的说明.docx",
        "没有书名号的文档.txt"
    ]

    for filename in test_cases:
        title = version_manager.extract_title_from_brackets(filename)
        print(f"文件名: {filename}")
        print(f"提取标题: {title}\n")


def test_check_revision_keywords():
    """测试检查修订关键词"""
    print("\n=== 测试修订关键词检查 ===")

    test_cases = [
        "关于修订《信贷管理办法》的通知.docx",
        "《客户服务规范》更新版.pdf",
        "《内部制度》新增补充说明.docx",
        "《正常文档》.txt"
    ]

    for filename in test_cases:
        has_revision = version_manager.check_revision_keywords(filename)
        print(f"文件名: {filename}")
        print(f"包含修订关键词: {has_revision}\n")


def test_find_similar_documents():
    """测试查找相似文档"""
    print("\n=== 测试查找相似文档 ===")

    db = get_db_session()

    try:
        # 查找一个包含"管理办法"的文档
        similar_docs = version_manager.find_similar_documents(
            db,
            "管理办法",
            BusinessCategory.HEADQUARTERS_ISSUE
        )

        print(f"找到 {len(similar_docs)} 个相似文档:")
        for doc in similar_docs[:5]:  # 只显示前5个
            print(f"  - {doc.imagefilename}")
            print(f"    文件ID: {doc.imagefileid}")
            print(f"    文档ID: {doc.document_id}")
            print()

    finally:
        db.close()


def test_check_expiration_by_metadata():
    """测试通过元数据检查文档过期"""
    print("\n=== 测试元数据过期检查 ===")

    db = get_db_session()

    try:
        # 查找一些已完成的非总行发文
        docs = db.query(OAFileInfo).filter(
            OAFileInfo.business_category != BusinessCategory.HEADQUARTERS_ISSUE,
            OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
            OAFileInfo.document_id.isnot(None)
        ).limit(5).all()

        print(f"检查 {len(docs)} 个文档的有效期:")
        for doc in docs:
            is_expired, expiration_info = version_manager.check_document_expiration_by_metadata(doc)
            print(f"\n文件名: {doc.imagefilename}")
            print(f"是否过期: {is_expired}")
            print(f"有效期信息: {expiration_info}")

    finally:
        db.close()


def test_process_headquarters_version_deduplication():
    """测试总行发文版本去重（模拟运行）"""
    print("\n=== 测试总行发文版本去重 ===")
    print("注意: 这是一个模拟测试，不会真正删除文档")
    print("如需真正运行，请确认数据备份后再执行")

    # 这里只显示会处理哪些文档
    db = get_db_session()

    try:
        headquarters_docs = db.query(OAFileInfo).filter(
            OAFileInfo.business_category == BusinessCategory.HEADQUARTERS_ISSUE,
            OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
            OAFileInfo.document_id.isnot(None)
        ).limit(10).all()

        print(f"\n找到 {len(headquarters_docs)} 个总行发文:")

        revision_count = 0
        for doc in headquarters_docs:
            has_revision = version_manager.check_revision_keywords(doc.imagefilename)
            title = version_manager.extract_title_from_brackets(doc.imagefilename)

            if has_revision and title:
                revision_count += 1
                print(f"\n可能的修订文档:")
                print(f"  文件名: {doc.imagefilename}")
                print(f"  标题: {title}")
                print(f"  文件ID: {doc.imagefileid}")

        print(f"\n总共找到 {revision_count} 个包含修订关键词的文档")

    finally:
        db.close()


def test_process_expiration_check():
    """测试文档有效期检查（模拟运行）"""
    print("\n=== 测试文档有效期检查 ===")
    print("注意: 这是一个模拟测试，不会真正删除文档")

    db = get_db_session()

    try:
        docs = db.query(OAFileInfo).filter(
            OAFileInfo.business_category != BusinessCategory.HEADQUARTERS_ISSUE,
            OAFileInfo.processing_status == ProcessingStatus.COMPLETED,
            OAFileInfo.document_id.isnot(None)
        ).limit(10).all()

        print(f"\n检查 {len(docs)} 个文档:")

        has_metadata_count = 0
        expired_count = 0

        for doc in docs:
            is_expired, expiration_info = version_manager.check_document_expiration_by_metadata(doc)

            if expiration_info:
                has_metadata_count += 1
                print(f"\n文件名: {doc.imagefilename}")
                print(f"  有效期: {expiration_info}")
                print(f"  是否过期: {is_expired}")

                if is_expired:
                    expired_count += 1

        print(f"\n统计:")
        print(f"  有有效期元数据的文档: {has_metadata_count}")
        print(f"  已过期的文档: {expired_count}")

    finally:
        db.close()


def main():
    """运行所有测试"""
    print("=" * 60)
    print("文档版本管理和有效期管理功能测试")
    print("=" * 60)

    try:
        # 1. 测试基础功能
        test_extract_title()
        test_check_revision_keywords()

        # 2. 测试数据库查询功能
        test_find_similar_documents()
        test_check_expiration_by_metadata()

        # 3. 测试主要处理流程（模拟）
        test_process_headquarters_version_deduplication()
        test_process_expiration_check()

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)

    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
