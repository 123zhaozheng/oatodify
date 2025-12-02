"""
DAT文件数据导入服务
用于从数据组提供的.dat文件中增量导入文件信息到oa_file_info表
"""

import glob
import logging
import os
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import OAFileInfo, BusinessCategory, ProcessingStatus
import json

logger = logging.getLogger(__name__)

# ASCII码为1的字符作为分隔符
DAT_DELIMITER = chr(1)


class DATImporter:
    """DAT文件导入器"""

    def __init__(self, dat_file_path: str):
        """
        初始化导入器

        Args:
            dat_file_path: DAT文件路径
        """
        self.dat_file_path = dat_file_path
        self.stats = {
            'total_lines': 0,
            'parsed_lines': 0,
            'new_records': 0,
            'updated_records': 0,
            'skipped_records': 0,
            'error_records': 0,
            'errors': []
        }

    def parse_dat_line(self, line: str) -> Dict:
        """
        解析DAT文件的一行数据

        Args:
            line: 一行数据

        Returns:
            解析后的字典
        """
        try:
            # 去除行尾空白字符
            line = line.rstrip('\n\r')

            if not line:
                return None

            # 使用ASCII码1作为分隔符进行分割
            fields = line.split(DAT_DELIMITER)

            # 根据DAT文件的字段顺序解析（需要根据实际情况调整）
            # 第一列不需要，所以所有索引+1
            # 字段顺序为：[跳过], imagefileid, business_category, is_zw, fj_imagefileid,
            #            imagefilename, imagefiletype, is_zip, filesize, asecode, tokenkey

            if len(fields) < 11:
                logger.warning(f"字段数量不足: {len(fields)} < 11")
                return None

            # 解析业务分类（索引从1变为2）
            try:
                business_category = BusinessCategory(fields[2].strip()) if fields[2].strip() else None
            except ValueError:
                logger.warning(f"无效的业务分类: {fields[2]}")
                business_category = None

            # 解析布尔值（索引+1）
            is_zw = fields[3].strip().lower() in ('1', 'true', 'yes', 't', 'y')
            is_zip = fields[7].strip().lower() in ('1', 'true', 'yes', 't', 'y')

            # 解析文件大小（索引从7变为8）
            try:
                filesize = int(fields[8].strip()) if fields[8].strip() else None
            except ValueError:
                filesize = None

            # 处理附件ID列表（索引从3变为4）
            fj_imagefileid = fields[4].strip() if fields[4].strip() else None
            # 如果附件ID不是JSON格式，尝试转换为JSON数组格式
            if fj_imagefileid and not fj_imagefileid.startswith('['):
                # 假设多个ID用逗号分隔
                fj_ids = [id.strip() for id in fj_imagefileid.split(',') if id.strip()]
                fj_imagefileid = json.dumps(fj_ids, ensure_ascii=False) if fj_ids else None

            return {
                'imagefileid': fields[1].strip(),
                'business_category': business_category,
                'is_zw': is_zw,
                'fj_imagefileid': fj_imagefileid,
                'imagefilename': fields[5].strip(),
                'imagefiletype': fields[6].strip() if fields[6].strip() else None,
                'is_zip': is_zip,
                'filesize': filesize,
                'asecode': fields[9].strip() if fields[9].strip() else None,
                'tokenkey': fields[10].strip() if fields[10].strip() else None,
            }

        except Exception as e:
            logger.error(f"解析行数据失败: {e}, line: {line[:100]}")
            return None

    def import_to_database(self, db: Session, update_existing: bool = False) -> Dict:
        """
        导入数据到数据库

        Args:
            db: 数据库会话
            update_existing: 是否更新已存在的记录

        Returns:
            导入统计信息
        """
        try:
            logger.info(f"开始导入DAT文件: {self.dat_file_path}")

            # 打开并读取DAT文件
            with open(self.dat_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    self.stats['total_lines'] += 1

                    # 解析行数据
                    data = self.parse_dat_line(line)

                    if data is None:
                        self.stats['skipped_records'] += 1
                        continue

                    self.stats['parsed_lines'] += 1

                    try:
                        # 检查记录是否已存在
                        existing_record = db.query(OAFileInfo).filter(
                            OAFileInfo.imagefileid == data['imagefileid']
                        ).first()

                        if existing_record:
                            if update_existing:
                                # 更新已存在的记录
                                for key, value in data.items():
                                    if value is not None:  # 只更新非空值
                                        setattr(existing_record, key, value)

                                existing_record.last_sync_at = datetime.now()
                                existing_record.updated_at = datetime.now()

                                self.stats['updated_records'] += 1
                                logger.debug(f"更新记录: {data['imagefileid']}")
                            else:
                                self.stats['skipped_records'] += 1
                                logger.debug(f"跳过已存在记录: {data['imagefileid']}")
                        else:
                            # 创建新记录
                            new_record = OAFileInfo(
                                **data,
                                processing_status=ProcessingStatus.PENDING,
                                sync_source='dat_import',
                                last_sync_at=datetime.now(),
                                created_at=datetime.now(),
                                updated_at=datetime.now()
                            )
                            db.add(new_record)
                            self.stats['new_records'] += 1
                            logger.debug(f"新增记录: {data['imagefileid']}")

                        # 每1000条提交一次
                        if (self.stats['parsed_lines'] % 1000) == 0:
                            db.commit()
                            logger.info(f"已处理 {self.stats['parsed_lines']} 条记录...")

                    except Exception as e:
                        self.stats['error_records'] += 1
                        error_msg = f"行 {line_num}: {str(e)}"
                        self.stats['errors'].append(error_msg)
                        logger.error(f"导入记录失败 {error_msg}")
                        db.rollback()
                        continue

            # 最后提交剩余的数据
            db.commit()

            logger.info(f"DAT文件导入完成: {self.stats}")
            return self.stats

        except FileNotFoundError:
            error_msg = f"DAT文件不存在: {self.dat_file_path}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            return self.stats

        except Exception as e:
            error_msg = f"导入过程发生异常: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            db.rollback()
            return self.stats


def import_dat_file(dat_file_path: str, db: Session, update_existing: bool = False) -> Dict:
    """
    导入DAT文件的便捷函数

    Args:
        dat_file_path: DAT文件路径
        db: 数据库会话
        update_existing: 是否更新已存在的记录

    Returns:
        导入统计信息
    """
    importer = DATImporter(dat_file_path)
    return importer.import_to_database(db, update_existing)


def _find_previous_day_directory(dat_directory: str) -> Tuple[str, str]:
    """找到上一天日期对应的子目录并返回目录路径及日期字符串"""
    if not os.path.isdir(dat_directory):
        raise FileNotFoundError(f"DAT文件根目录不存在: {dat_directory}")

    target_date = (datetime.now() - timedelta(days=1)).date()
    normalized_target = target_date.strftime("%Y%m%d")

    matching_directories: List[str] = []
    with os.scandir(dat_directory) as entries:
        for entry in entries:
            if not entry.is_dir():
                continue

            digits_only = ''.join(ch for ch in entry.name if ch.isdigit())
            if digits_only == normalized_target:
                matching_directories.append(entry.path)

    if not matching_directories:
        raise FileNotFoundError(
            f"在目录 {dat_directory} 中未找到日期 {target_date.isoformat()} 对应的子目录"
        )

    selected_directory = max(matching_directories, key=os.path.getmtime)
    return selected_directory, target_date.isoformat()


def get_latest_dat_file(dat_directory: str) -> str:
    """
    获取上一天目录中最新的DAT文件

    Args:
        dat_directory: DAT文件根目录（包含按日期命名的子目录）

    Returns:
        上一天日期目录中的最新DAT文件完整路径
    """

    target_directory, target_date_str = _find_previous_day_directory(dat_directory)

    dat_files = [
        *glob.glob(os.path.join(target_directory, "*.dat")),
        *glob.glob(os.path.join(target_directory, "*.DAT")),
    ]
    dat_files = [file_path for file_path in dat_files if os.path.isfile(file_path)]

    if not dat_files:
        raise FileNotFoundError(
            f"在日期目录 {target_directory} 中未找到.dat文件 (目标日期: {target_date_str})"
        )

    latest_file = max(dat_files, key=os.path.getmtime)

    logger.info(f"找到日期 {target_date_str} 的DAT文件: {latest_file}")
    return latest_file
