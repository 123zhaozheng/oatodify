"""
测试手动触发API接口
"""
import requests
import time
import json

# 配置
BASE_URL = "http://localhost:8000"  # 根据实际情况修改


def test_clean_version_duplicates():
    """测试手动清理版本重复"""
    print("\n" + "=" * 60)
    print("测试: 手动清理总行发文版本重复")
    print("=" * 60)

    # 提交任务
    print("\n1. 提交清理任务...")
    response = requests.post(
        f"{BASE_URL}/maintenance/clean-version-duplicates",
        params={"limit": 10}  # 测试时使用小的limit值
    )

    if response.status_code != 200:
        print(f"❌ 任务提交失败: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    print(f"✅ 任务已提交")
    print(f"   消息: {result['message']}")
    print(f"   任务ID: {result['task_id']}")

    return result['task_id']


def test_clean_expired_documents():
    """测试手动清理过期文档"""
    print("\n" + "=" * 60)
    print("测试: 手动清理过期文档")
    print("=" * 60)

    # 提交任务
    print("\n1. 提交清理任务...")
    response = requests.post(
        f"{BASE_URL}/maintenance/clean-expired-documents",
        params={"limit": 10}  # 测试时使用小的limit值
    )

    if response.status_code != 200:
        print(f"❌ 任务提交失败: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    print(f"✅ 任务已提交")
    print(f"   消息: {result['message']}")
    print(f"   任务ID: {result['task_id']}")

    return result['task_id']


def check_task_status(task_id, task_name="任务"):
    """查询任务状态"""
    print(f"\n2. 查询{task_name}状态...")
    response = requests.get(f"{BASE_URL}/maintenance/task-status/{task_id}")

    if response.status_code != 200:
        print(f"❌ 查询失败: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    print(f"   状态: {result['state']}")
    print(f"   是否完成: {result['ready']}")

    if result['ready']:
        if result['successful']:
            print(f"   ✅ {task_name}成功完成!")
            print(f"\n   处理结果:")
            print(json.dumps(result['result'], indent=2, ensure_ascii=False))
        else:
            print(f"   ❌ {task_name}失败!")
            print(f"   错误: {result.get('error', '未知错误')}")
    else:
        info = result.get('info', '任务正在执行中...')
        print(f"   进度: {info}")

    return result


def wait_for_task(task_id, task_name="任务", max_wait=60):
    """等待任务完成"""
    print(f"\n3. 等待{task_name}完成（最多{max_wait}秒）...")
    start_time = time.time()
    check_count = 0

    while time.time() - start_time < max_wait:
        check_count += 1
        status = check_task_status(task_id, task_name)

        if not status:
            break

        if status['ready']:
            elapsed = int(time.time() - start_time)
            print(f"\n✅ {task_name}完成，总耗时: {elapsed} 秒")
            return status

        wait_time = 5
        print(f"   第 {check_count} 次检查，等待 {wait_time} 秒后再次查询...")
        time.sleep(wait_time)

    print(f"\n⏰ 等待超时（超过 {max_wait} 秒）")
    return None


def test_api_connectivity():
    """测试API连接性"""
    print("\n" + "=" * 60)
    print("测试: API连接性")
    print("=" * 60)

    try:
        # 尝试访问API文档
        response = requests.get(f"{BASE_URL}/docs")
        if response.status_code == 200:
            print(f"✅ API服务正常运行")
            print(f"   API文档地址: {BASE_URL}/docs")
            return True
        else:
            print(f"❌ API服务异常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到API服务: {e}")
        print(f"   请确认服务地址: {BASE_URL}")
        return False


def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("手动触发API接口测试")
    print("=" * 60)
    print(f"API地址: {BASE_URL}")
    print("=" * 60)

    # 1. 测试连接性
    if not test_api_connectivity():
        print("\n❌ API服务不可用，测试终止")
        return

    # 2. 测试版本去重API
    task_id_1 = test_clean_version_duplicates()
    if task_id_1:
        wait_for_task(task_id_1, "版本去重任务", max_wait=120)

    # 等待一段时间再执行下一个任务
    print("\n等待10秒后执行下一个任务...")
    time.sleep(10)

    # 3. 测试过期文档清理API
    task_id_2 = test_clean_expired_documents()
    if task_id_2:
        wait_for_task(task_id_2, "过期文档清理任务", max_wait=120)

    print("\n" + "=" * 60)
    print("所有测试完成!")
    print("=" * 60)


def quick_test():
    """快速测试（只提交任务，不等待完成）"""
    print("\n" + "=" * 60)
    print("快速测试: 只提交任务")
    print("=" * 60)

    # 测试连接
    if not test_api_connectivity():
        return

    # 提交版本去重任务
    task_id_1 = test_clean_version_duplicates()
    if task_id_1:
        print(f"\n可以使用以下命令查询任务状态:")
        print(f"curl {BASE_URL}/maintenance/task-status/{task_id_1}")

    # 提交过期文档清理任务
    task_id_2 = test_clean_expired_documents()
    if task_id_2:
        print(f"\n可以使用以下命令查询任务状态:")
        print(f"curl {BASE_URL}/maintenance/task-status/{task_id_2}")


if __name__ == "__main__":
    import sys

    print("\n请选择测试模式:")
    print("1. 完整测试（会等待任务完成）")
    print("2. 快速测试（只提交任务）")

    choice = input("\n请输入选择 (1/2，默认2): ").strip() or "2"

    if choice == "1":
        main()
    else:
        quick_test()
