import hashlib
import zipfile
import io
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class DecryptionService:
    """文档解密服务"""
    
    @staticmethod
    def decrypt_binary_data(encrypted_data: bytes, password: str) -> bytes:
        """
        直接解密二进制数据并返回解密后的数据
        
        Args:
            encrypted_data: 加密的二进制数据 (bytes)
            password: 解密密码 (str)
        
        Returns:
            bytes: 解密后的数据
        """
        try:
            # 导入解密库
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
            
            logger.info(f"🔍 原始数据大小: {len(encrypted_data)} 字节")
            logger.info(f"🔍 数据开头: {encrypted_data[:20]}")
            logger.info(f"🔑 使用密码: {'*' * len(password)}")
            
            # 检查数据是否已经是ZIP格式
            if encrypted_data.startswith(b'PK\x03\x04'):
                logger.info("⚠️  数据开头是ZIP文件头，可能无需解密")
                logger.info("🔄 直接返回原始数据...")
                
                # 验证ZIP文件
                if DecryptionService._verify_zip_data(encrypted_data):
                    logger.info("✅ 文件已验证为有效ZIP文件！")
                    return encrypted_data
                else:
                    logger.info("❌ 直接验证失败，继续尝试解密...")
            
            # 生成AES密钥 (模拟Java的方式)
            logger.info("\n🔐 开始AES解密过程...")
            key = DecryptionService._generate_aes_key(password)
            logger.info(f"🔑 生成的密钥: {key.hex()}")
            
            # 检查数据长度是否符合AES块大小
            if len(encrypted_data) % 16 != 0:
                logger.warning(f"⚠️  数据长度 {len(encrypted_data)} 不是16的倍数，可能不是AES加密数据")
            
            # 创建AES解密器 (ECB模式)
            cipher = AES.new(key, AES.MODE_ECB)
            
            # 执行解密
            logger.info("🔓 执行解密...")
            decrypted_data = cipher.decrypt(encrypted_data)
            logger.info(f"✅ 解密完成，得到 {len(decrypted_data)} 字节")
            
            # 尝试移除PKCS7填充
            try:
                unpadded_data = unpad(decrypted_data, AES.block_size)
                logger.info(f"✅ 移除填充成功，最终数据 {len(unpadded_data)} 字节")
                decrypted_data = unpadded_data
            except ValueError as e:
                logger.warning(f"⚠️  填充移除失败: {e}")
                logger.info("📋 尝试使用原始解密数据...")
            
            # 检查解密结果
            logger.info(f"🔍 解密数据开头: {decrypted_data[:20]}")
            
            if decrypted_data.startswith(b'PK\x03\x04'):
                logger.info("🎉 解密成功！检测到ZIP文件头")
            elif decrypted_data.startswith(b'PK\x05\x06'):
                logger.info("🎉 解密成功！检测到ZIP文件尾")
            else:
                logger.warning("❓ 解密结果不是标准ZIP格式，但仍返回数据...")
            
            return decrypted_data
                
        except ImportError:
            logger.error("❌ 需要安装加密库: pip install pycryptodome")
            raise ImportError("需要安装加密库: pip install pycryptodome")
        except Exception as e:
            logger.error(f"❌ 解密过程出错: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    @staticmethod
    def _generate_aes_key(password: str) -> bytes:
        """
        生成AES密钥 - 兼容Java版本
        使用SHA-256生成128位密钥
        """
        return hashlib.sha256(password.encode('utf-8')).digest()[:16]
    
    @staticmethod
    def _verify_zip_data(data: bytes) -> bool:
        """验证二进制数据是否为有效ZIP文件"""
        try:
            with zipfile.ZipFile(io.BytesIO(data), 'r') as zip_ref:
                file_list = zip_ref.namelist()
                logger.info(f"📦 ZIP包含 {len(file_list)} 个文件")
                
                # 显示前5个文件
                for filename in file_list[:5]:
                    try:
                        info = zip_ref.getinfo(filename)
                        logger.info(f"   📄 {filename} ({info.file_size} 字节)")
                    except:
                        logger.info(f"   📄 {filename}")
                
                if len(file_list) > 5:
                    logger.info(f"   ... 还有 {len(file_list) - 5} 个文件")
                
                return True
                
        except zipfile.BadZipFile as e:
            logger.error(f"❌ ZIP文件格式错误: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ ZIP验证出错: {e}")
            return False
    
    @staticmethod
    def extract_zip_files(zip_data: bytes) -> bytes:
        """
        提取ZIP文件中唯一文件的二进制内容。

        假设ZIP内只有一个文件且文件名无需返回，只返回解出的二进制数据。

        Returns:
            bytes: ZIP内文件的二进制内容
        """
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zip_ref:
                # 过滤出非目录条目
                file_names = [name for name in zip_ref.namelist() if not name.endswith('/')]

                if not file_names:
                    raise ValueError("ZIP文件中未找到文件")

                if len(file_names) > 1:
                    logger.warning(f"ZIP内含 {len(file_names)} 个文件，按约定仅取第一个")

                first_file = file_names[0]
                file_content = zip_ref.read(first_file)
                logger.info(f"提取文件(首个): {first_file} ({len(file_content)} 字节)")
                return file_content

        except Exception as e:
            logger.error(f"提取ZIP文件失败: {e}")
            raise

# 创建全局实例
decryption_service = DecryptionService()
