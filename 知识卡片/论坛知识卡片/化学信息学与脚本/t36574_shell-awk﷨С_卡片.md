---
key: t36574
title: shell���-awk�﷨С��
url: http://bbs.keinsci.com/thread-36574-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2023
cards: 25
---

# shell���-awk�﷨С�� — 知识卡片

## 1. awk 基本语法结构

awk 命令的基本语法结构由选项、模式和动作组成。结构形式为 `awk [选项] 'pattern1 {action1} pattern2 {action2}...' file`。该工具对输入文件或标准输入的数据逐行进行处理，默认的字段分隔符为 "tab" 或 "空格"。

---

## 2. awk 常用选项

awk 提供了两个常用选项来控制输入和变量。`-F` 用于指定文件数据的分隔符，其功能等同于语法中的 `BEGIN{FS="分隔符"}`。`-v` 用于将用户自定义的外部变量传入 awk 内部，使用格式为 `awk -v myvar="${global_var}" '{action}' file`。

---

## 3. awk 常用模式 (Pattern)

awk 中的模式用于筛选需要处理的数据行。常用的模式包括正则表达式（如 `/^[0-9]+/`）、字段引用（`$n` 表示第 n 字段，`$0` 表示当前整行）、逻辑与关系运算符（`&&`, `||`, `!`, `~`, `!~`, `<`, `>`, `==` 等）以及特殊块 `BEGIN{}` 和 `END{}`。

---

## 4. awk 基础示例：字段匹配与筛选

通过指定模式可以筛选出符合条件的行。例如，`awk '$1=="Beta"' test.dat` 筛选第一字段为 "Beta" 的行；`awk '$1 ~ /^[a-z]+$/' test.dat` 筛选第一字段全为小写字母的行；`awk '$3 > 50' test.dat` 筛选第三字段值大于 50 的行。

---

## 5. awk 中的 BEGIN 和 END 块

`BEGIN{}` 块在读取文件之前执行，常用于初始化变量或打印表头；`END{}` 块在处理完所有文件记录后执行，常用于输出最终结果。示例 `awk 'BEGIN{print "File processing is beginning.."}{print}END{print "All work has been done~"}' test.dat` 展示了这一流程。

---

## 6. awk 内置变量

awk 提供了多个内置变量来获取行号、字段数等信息。`$n` 表示第 n 个字段，`$0` 表示当前整行。`FILENAME` 为当前文件名，`NR` 为已处理的记录总数（跨文件累加），`FNR` 为当前文件的记录数（每个文件重置），`NF` 为当前行的字段数，`FS` 和 `RS` 分别为字段和记录分隔符。

---

## 7. awk 内置变量应用示例

结合内置变量可以进行复杂的数据统计和格式化输出。例如，使用 `NR` 和 `NF` 统计前几行的数据并在 END 块中计算平均值：`awk 'BEGIN{...}NR<4{...}END{...}' test.dat`。其中 `OFS` 和 `ORS` 控制输出时的字段和记录分隔符。

---

## 8. awk 数学函数

awk 支持常见的数学运算函数。包括 `sin(x)`, `cos(x)`, `atan2(y,x)`, `exp(x)`, `log(x)` (自然对数), `sqrt(x)` (平方根), `int(x)` (取整)。

---

## 9. awk 字符串替换函数

`sub(regexp, replacement [,string])` 和 `gsub(regexp, replacement [,string])` 用于字符串替换。`sub` 仅替换第一次匹配到的内容，而 `gsub` 会替换所有匹配到的内容。若未指定 string 参数，默认对 `$0` 进行操作。

---

## 10. awk 字符串截取函数

`substr(string, start [, length])` 用于从字符串 string 的 start 位置开始截取长度为 length 的子串。若省略 length 参数，则截取到字符串末尾。

---

## 11. awk 数组排序函数

`asort(source)` 和 `asorti(source)` 用于对数组进行排序。`asort` 对数组的值进行排序并丢弃原索引，`asorti` 对数组的索引进行排序。排序后数组的索引变为从 1 开始的连续整数。

---

## 12. awk 字符串查找与长度函数

`index(in, find)` 返回字符串 find 在字符串 in 中首次出现的位置（从 1 开始）。`length([string])` 返回字符串的字符个数。若参数为数字表达式且不加引号，awk 会先计算数值再将其转为字符串统计长度（如 `length(3 * 2)` 结果为 1）。

---

## 13. awk 正则匹配与分割函数

`match(string, regexp)` 返回字符串中匹配正则表达式 regexp 的最长子串的起始位置，未匹配则返回 0。`split(string, array, [seps])` 使用分隔符 seps 将字符串 string 分割并存入数组 array，返回分割的段数。

---

## 14. awk 字符串大小写转换函数

`toupper(string)` 将字符串中的小写字母转换为大写字母。`tolower(string)` 将字符串中的大写字母转换为小写字母。非字母字符保持不变。

---

## 15. awk 输出格式化

`print` 和 `printf` 用于输出，`printf` 支持格式化控制。常用格式符包括 `%d` (十进制整数), `%f` (浮点数, 如 `%-5.3f` 表示左对齐、总宽 5、保留 3 位小数), `%e` (科学计数法), `%s` (字符串)。

---

## 16. awk 条件判断语句

awk 支持 `if`, `if-else`, 以及 `else if` 结构来实现多重条件判断。当 action 块内只有一条语句时，花括号 `{}` 可以省略，但多条语句必须用花括号括起并用分号 `;` 分隔。

---

## 17. awk 三元运算符

awk 支持 C 风格的三元运算符 `condition ? action1 : action2`。例如 `max=($1 > $2) ? $1 : $2` 表示如果 `$1` 大于 `$2`，则将 `$1` 赋值给 max，否则将 `$2` 赋值给 max。

---

## 18. awk 循环语句

awk 支持 `while`, `for`, `break`, `continue` 循环控制语句。`for` 循环常用于遍历字段，如 `awk '{for (i=1; i<=NF; i++) {print $i}}' file`。`next` 语句用于跳过当前记录的处理，直接读取下一行。

---

## 19. awk 关联数组

awk 支持关联数组，索引可以是数字或字符串。定义格式为 `a[index]="value"`。判断索引是否存在使用 `if (index in a)`。遍历数组推荐使用 `for (i in a)`。删除数组元素使用 `delete a[index]`。

---

## 20. awk 实用技巧：区间提取

利用正则表达式范围可以提取文件中特定区间的行。例如，提取 CP2K restart 文件中速度部分的命令为：`awk '/&VELOCITY/, /&END VELOCITY/{if (!/&VELOCITY/ && !/&END VELOCITY/) print}' test-1.restart`。

---

## 21. awk 实用技巧：字符串拼接与变量赋值

awk 支持字符串拼接和直接在命令行中赋值变量。拼接示例：`echo "A" | awk '{b=$1"_1"; print b}'`。变量赋值示例：`awk '{if($1!="#!") print $2, exp(($4-bmax)/kbt)}' kbt=2.494339 bmax=23 file.dat`。

---

## 22. awk 实用技巧：数值统计

awk 常用于列数据的统计运算。求某一列最大值：`awk 'BEGIN{max=0}{if ($1 > max) max=$1}END{print max}' test.dat`。求和：`awk '{sum+=$1}END{print sum}' test.dat`。按列求和：`awk '{for(i=1; i<=NF; i++) sum[i] += $i}END {for(i=1; i<=NF; i++) print sum[i]}' file`。

---

## 23. awk 实用技巧：多文件合并

awk 可以利用 `NR` 和 `FNR` 的特性将两个文件的行合并。例如：`awk 'NR==FNR{a[FNR]=$0;next}{print a[FNR],"\t",$0}' file1 file2 > merged.dat`。这将把 file1 和 file2 对应的行合并到一行中。

---

## 24. Shell 脚本：xyz 文件原子后缀添加

该 Shell 脚本结合 awk 用于给 xyz 格式文件中指定序号的原子添加后缀（如 `_1`）。脚本读取用户输入的原子序号（支持 `2,3,5-9` 格式）和后缀符号，利用 awk 的数组和 `sub` 函数修改指定原子的名称，并将结果输出到 `coord_new.xyz`。

---

## 25. xyz 原子后缀添加脚本中的 awk 逻辑

脚本中的 awk 部分首先解析输入的原子序号字符串，将其转换为数组索引。随后逐行读取 xyz 文件，根据 `NR`（行号）判断是否为原子行，并检查原子序号是否在之前解析的数组中。如果在，则使用 `sub($1, $1sym)` 替换原子名称，最后按指定格式输出坐标。
