/**
 * LeetCode 45 - 跳跃游戏 II
 * ===========================
 * 贪心 + BFS层序思想
 * 时间: O(n)  空间: O(1)
 */

#include <vector>
#include <algorithm>
using namespace std;

class Solution {
public:
    int jump(vector<int>& nums) {
        int n = nums.size();
        if (n <= 1) return 0;   // 已经在终点，不需要跳

        int jumps = 0;          // 已经跳的次数
        int cur_end = 0;        // 当前这一跳能到达的最远边界
        int farthest = 0;       // 下一跳能到达的最远位置

        // 注意: 遍历到 n-2 即可，因为题目保证能到终点
        for (int i = 0; i < n - 1; i++) {
            // 在到达 cur_end 之前，不断探索下一跳的极限
            farthest = max(farthest, i + nums[i]);

            // 到达当前跳跃的边界 → 必须跳了
            if (i == cur_end) {
                jumps++;
                cur_end = farthest;

                // 如果下一跳已经能覆盖终点，提前结束
                if (cur_end >= n - 1) break;
            }
        }

        return jumps;
    }
};


// ============================================================
// 测试代码
// ============================================================
#include <iostream>

int main() {
    Solution sol;

    // 测试用例
    vector<pair<vector<int>, int>> tests = {
        {{2, 3, 1, 1, 4}, 2},
        {{2, 3, 0, 1, 4}, 2},
        {{1, 2, 3}, 2},
        {{0}, 0},
        {{1, 2}, 1},
        {{3, 2, 1, 0, 4}, 2},
    };

    bool all_pass = true;
    for (auto& [nums, expected] : tests) {
        int result = sol.jump(const_cast<vector<int>&>(nums));
        bool pass = (result == expected);
        all_pass &= pass;

        cout << "nums = [";
        for (int i = 0; i < nums.size(); i++) {
            cout << nums[i] << (i < nums.size()-1 ? ", " : "");
        }
        cout << "]  ->  " << result
             << "  (预期 " << expected << ")  "
             << (pass ? "PASS!" : "FAIL!")
             << endl;
    }

    cout << "\n========================================" << endl;
    cout << (all_pass ? "  咕咕嘎嘎！全部通过~~" : "  有测试失败了，呜呜") << endl;
    cout << "========================================" << endl;

    return 0;
}
