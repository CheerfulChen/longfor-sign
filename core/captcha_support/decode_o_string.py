def decode_o_string(o_string: str) -> list:
    """
    将 o 字符串（如 "dingxiang85b86927..."）转换为切片顺序数组

    算法逻辑：
    1. 遍历字符串的前32个字符
    2. 对每个字符取 ASCII 码
    3. 计算 charCode % 32
    4. 如果这个值已存在数组中，就递增 charCode 直到不重复
    5. 推入数组

    Args:
        o_string: API 返回的 o 字符串

    Returns:
        切片顺序数组（0-31的整数列表）
    """
    if not o_string:
        return []

    result = []

    for i in range(len(o_string)):
        # 只处理前32个字符
        if i == 32:
            break

        # 获取字符的 ASCII 码
        char_code = ord(o_string[i])

        # 计算 charCode % 32，如果重复就递增
        mod_value = char_code % 32
        while mod_value in result:
            char_code += 1
            mod_value = char_code % 32

        # 推入结果数组
        result.append(mod_value)

    return result
