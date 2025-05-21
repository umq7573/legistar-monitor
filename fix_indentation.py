#!/usr/bin/env python3

with open('generate_web_page.py', 'r') as f:
    lines = f.readlines()

fixed_lines = []
for line_num, line in enumerate(lines):
    # Fix the specific indentation issue at line 273-279
    if 273 <= line_num + 1 <= 279:
        # Remove current indentation and add 4 spaces (consistent with surrounding code)
        fixed_line = '    ' + line.lstrip()
        fixed_lines.append(fixed_line)
    # Fix the extra newline before HTML closing div (line 280-281)
    elif line_num + 1 == 280:
        # Keep the same line but remove extra spacing at beginning
        fixed_lines.append('    ' + line.lstrip())
    else:
        fixed_lines.append(line)

with open('generate_web_page.py', 'w') as f:
    f.writelines(fixed_lines)

print("Indentation fixed in generate_web_page.py") 