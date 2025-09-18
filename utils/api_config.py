"""
API配置管理模块
用于统一管理前端到后端的API调用配置
"""
import os
from typing import Optional

class APIConfig:
    """API配置类"""
    
    def __init__(self):
        self._base_url: Optional[str] = None
    
    @property
    def base_url(self) -> str:
        """获取API基础URL"""
        if self._base_url is None:
            # 优先使用环境变量
            api_url = os.getenv("API_BASE_URL")
            
            if api_url:
                self._base_url = api_url.rstrip('/')
            else:
                # 根据运行环境自动检测
                if self._is_running_in_docker():
                    # Docker环境中使用服务名
                    self._base_url = "http://api:8000"
                else:
                    # 开发环境使用localhost
                    self._base_url = "http://localhost:18000"
        
        return self._base_url
    
    def _is_running_in_docker(self) -> bool:
        """检测是否在Docker容器中运行"""
        try:
            # 检查Docker容器标识文件
            if os.path.exists('/.dockerenv'):
                return True
            
            # 检查cgroup信息
            if os.path.exists('/proc/1/cgroup'):
                with open('/proc/1/cgroup', 'r') as f:
                    content = f.read()
                    if 'docker' in content or 'containerd' in content:
                        return True
            
            # 检查hostname是否为容器名
            hostname = os.getenv('HOSTNAME', '')
            if hostname.startswith('oa-'):
                return True
                
            return False
        except Exception:
            return False
    
    def get_url(self, endpoint: str) -> str:
        """获取完整的API URL"""
        endpoint = endpoint.lstrip('/')
        return f"{self.base_url}/{endpoint}"
    
    def health_check_url(self) -> str:
        """获取健康检查URL"""
        return self.get_url("health")
    
    def files_url(self, endpoint: str = "") -> str:
        """获取文件相关API URL"""
        base = "api/v1/files"
        if endpoint:
            endpoint = endpoint.lstrip('/')
            return self.get_url(f"{base}/{endpoint}")
        return self.get_url(base)
    
    def statistics_url(self, endpoint: str = "") -> str:
        """获取统计相关API URL"""
        base = "api/v1/statistics"
        if endpoint:
            endpoint = endpoint.lstrip('/')
            return self.get_url(f"{base}/{endpoint}")
        return self.get_url(base)

# 全局API配置实例
api_config = APIConfig()

# 便捷函数
def get_api_url(endpoint: str) -> str:
    """获取API URL的便捷函数"""
    return api_config.get_url(endpoint)

def get_files_api_url(endpoint: str = "") -> str:
    """获取文件API URL的便捷函数"""
    return api_config.files_url(endpoint)

def get_statistics_api_url(endpoint: str = "") -> str:
    """获取统计API URL的便捷函数"""
    return api_config.statistics_url(endpoint)

def get_health_check_url() -> str:
    """获取健康检查URL的便捷函数"""
    return api_config.health_check_url()
