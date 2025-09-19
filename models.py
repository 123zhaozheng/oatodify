from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from enum import Enum
from datetime import datetime

Base = declarative_base()

class BusinessCategory(str, Enum):
    HEADQUARTERS_ISSUE = "headquarters_issue"  # 总行发文
    RETAIL_ANNOUNCEMENT = "retail_announcement"  # 零售条线公告
    PUBLICATION_RELEASE = "publication_release"  # 刊物发布
    BRANCH_ISSUE = "branch_issue"  # 支行发文
    BRANCH_RECEIVE = "branch_receive"  # 支行收文
    PUBLIC_STANDARD = "public_standard"  # 公共发布及规范文件
    HEADQUARTERS_RECEIVE = "headquarters_receive"  # 总行收文
    CORPORATE_ANNOUNCEMENT = "corporate_announcement"  # 公司条线公告

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DECRYPTING = "decrypting"
    PARSING = "parsing"
    ANALYZING = "analyzing"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class OAFileInfo(Base):
    """OA系统文件信息模型"""
    
    __tablename__ = "oa_file_info"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 基础信息
    imagefileid = Column(String(100), nullable=False, unique=True, index=True, comment="文件ID")
    business_category = Column(SQLEnum(BusinessCategory), nullable=False, comment="业务分类")
    is_zw = Column(Boolean, nullable=False, default=False, comment="是否正文")
    fj_imagefileid = Column(Text, comment="附件文件ID列表（JSON格式，如果是正文的话）")
    imagefilename = Column(String(500), nullable=False, comment="文件名（包含后缀）")
    imagefiletype = Column(String(50), comment="文档类型")
    is_zip = Column(Boolean, default=False, comment="是否压缩文件")
    filesize = Column(Integer, comment="文件大小（字节）")
    asecode = Column(String(255), comment="OSS下载解密code")
    tokenkey = Column(String(500), comment="OSS下载key")
    
    # 处理状态
    processing_status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING, 
                              nullable=False, comment="处理状态")
    processing_message = Column(Text, comment="处理消息")
    processing_started_at = Column(DateTime, comment="开始处理时间")
    processing_completed_at = Column(DateTime, comment="完成处理时间")
    
    # AI分析结果
    ai_analysis_result = Column(Text, comment="AI分析结果（JSON格式）")
    ai_confidence_score = Column(Integer, comment="AI置信度（0-100）")
    should_add_to_kb = Column(Boolean, comment="是否应该加入知识库")
    
    # 关联的Document ID（处理成功后）
    document_id = Column(Integer, comment="关联的documents表ID")
    
    # 同步信息
    sync_source = Column(String(50), default="oa_system", comment="同步来源")
    last_sync_at = Column(DateTime, default=func.now(), comment="最后同步时间")
    
    # 错误信息
    error_count = Column(Integer, default=0, comment="错误次数")
    last_error = Column(Text, comment="最后错误信息")
    
    # 时间戳
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<OAFileInfo(id={self.id}, filename={self.imagefilename}, status={self.processing_status})>"

class ProcessingLog(Base):
    """处理日志模型"""
    
    __tablename__ = "processing_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String(100), nullable=False, index=True, comment="文件ID")
    step = Column(String(50), nullable=False, comment="处理步骤")
    status = Column(String(20), nullable=False, comment="步骤状态")
    message = Column(Text, comment="处理消息")
    duration_seconds = Column(Integer, comment="处理耗时（秒）")
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<ProcessingLog(file_id={self.file_id}, step={self.step}, status={self.status})>"
