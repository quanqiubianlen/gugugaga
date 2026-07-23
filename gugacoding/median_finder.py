"""
数据流的中位数 —— 双堆法实现
================================
插入: O(log n)
获取中位数: O(1)

思路：
  - large: 小顶堆，存较大的一半数字
  - small: 大顶堆（用负数模拟），存较小的一半数字
  - 保持 len(small) <= len(large) <= len(small) + 1
"""

import heapq


class MedianFinder:
    def __init__(self):
        self.small = []   # 大顶堆（存负数模拟），放较小的一半
        self.large = []   # 小顶堆，放较大的一半

    def add_num(self, num: int) -> None:
        """
        添加一个数字到数据流中
        时间复杂度: O(log n)
        """
        # 先把 num 放进 small（大顶堆），取 small 的最大值放到 large
        heapq.heappush(self.small, -num)

        # 保证 small 的最大值 <= large 的最小值
        if self.small and self.large and (-self.small[0] > self.large[0]):
            val = -heapq.heappop(self.small)
            heapq.heappush(self.large, val)

        # 平衡两个堆的大小
        if len(self.small) > len(self.large):
            val = -heapq.heappop(self.small)
            heapq.heappush(self.large, val)

        if len(self.large) > len(self.small) + 1:
            val = heapq.heappop(self.large)
            heapq.heappush(self.small, -val)

    def find_median(self) -> float:
        """
        返回当前数据流的中位数
        时间复杂度: O(1)
        """
        if len(self.large) > len(self.small):
            return float(self.large[0])
        else:
            return (self.large[0] - self.small[0]) / 2.0


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    mf = MedianFinder()

    print("=" * 50)
    print("  数据流中位数测试  ~(^_^)~")
    print("=" * 50)

    # 测试用例 1: 基本功能
    print("\n[测试1] 依次插入 [5, 2, 8, 1, 9]")
    nums1 = [5, 2, 8, 1, 9]
    for n in nums1:
        mf.add_num(n)
        print(f"   添加 {n} -> 中位数 = {mf.find_median()}")

    # 重置
    mf = MedianFinder()

    # 测试用例 2: 偶数个元素
    print("\n[测试2] 依次插入 [1, 2, 3, 4]（偶数个）")
    for n in [1, 2, 3, 4]:
        mf.add_num(n)
        print(f"   添加 {n} -> 中位数 = {mf.find_median()}")
    print(f"   预期: (2+3)/2 = 2.5  {'PASS!' if mf.find_median() == 2.5 else 'FAIL!'}")

    # 重置
    mf = MedianFinder()

    # 测试用例 3: LeetCode 经典用例
    print("\n[测试3] LeetCode 示例")
    print("   addNum(1) ->", end=" ")
    mf.add_num(1)
    print(f"中位数 = {mf.find_median()}  (预期 1.0)")

    print("   addNum(2) ->", end=" ")
    mf.add_num(2)
    print(f"中位数 = {mf.find_median()}  (预期 1.5)")

    print("   addNum(3) ->", end=" ")
    mf.add_num(3)
    print(f"中位数 = {mf.find_median()}  (预期 2.0)")

    # 重置
    mf = MedianFinder()

    # 测试用例 4: 100个随机数 vs 排序法
    import random
    print("\n[测试4] 100 个随机数，对比排序法")
    random.seed(42)
    data = [random.randint(1, 1000) for _ in range(100)]
    for n in data:
        mf.add_num(n)
    expected = sorted(data)[49:51]
    expected_median = (expected[0] + expected[1]) / 2
    print(f"   双堆法结果: {mf.find_median()}")
    print(f"   排序法结果: {expected_median}")
    ok = abs(mf.find_median() - expected_median) < 0.001
    print(f"   {'PASS!' if ok else 'FAIL!'}")

    print("\n" + "=" * 50)
    print("  咕咕嘎嘎！测试全部完成~~")
    print("=" * 50)
