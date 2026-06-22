import asyncio, aiomysql, json

FEEDBACK = '得分34/52，正确率65.4%。选择题部分表现较好，基础概念掌握扎实；编程填空题存在多处细节错误，特别是变量命名大小写敏感问题突出。建议加强Python标识符规范训练，注意区分大小写，多进行代码调试练习。'
GENERATED_BY = '星辰智能体'

DETAIL = json.dumps({
    "questions": [
        {"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": False},
        {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "4", "score": 0, "max_score": 2, "comment": "答案为C，标准答案为A", "correct": False},
        {"index": "5", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": False},
        {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "9", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": False},
        {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "13. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "13. (2)", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": False},
        {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "14. (1)", "score": 0, "max_score": 2, "comment": "答案为D，标准答案为A", "correct": False},
        {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "14. (2) ②", "score": 0, "max_score": 2, "comment": "答案为sm.t = sd，标准答案为sm.year = sd，属性名错误", "correct": False},
        {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
        {"index": "15. (2) ②", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": False},
        {"index": "15. (3)", "score": 0, "max_score": 2, "comment": "答案为0 total = 0，标准答案为0，多余内容导致错误", "correct": False},
        {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "答案为OP = queinfo[k][i]，标准答案为op = queinfo[k][i]，变量名大小写错误，Python区分大小写", "correct": False},
        {"index": "15. (3) ②", "score": 0, "max_score": 2, "comment": "答案为queinfo[k][0] = data[P][3]，标准答案为queinfo[k][0] = data[p][3]，变量P大小写错误", "correct": False}
    ],
    "confidence": 0.88,
    "issues": [
        "第2题选择题答案错误", "第4题选择题答案错误", "第7题选择题答案错误",
        "第9题选择题答案错误", "第13.(2)题答案错误", "第14.(1)题答案错误",
        "第14.(2)②属性名错误", "第15.(2)②答案错误", "第15.(3)题多余内容",
        "第15.(3)①变量名大小写错误", "第15.(3)②变量名大小写错误"
    ]
}, ensure_ascii=False)

async def main():
    # Try different charsets
    for charset in ['utf8mb4', 'utf8', 'gbk']:
        print(f'\n=== Trying charset={charset} ===')
        try:
            conn = await aiomysql.connect(
                host='localhost', port=3306,
                user='study_monitor', password='study_monitor_2026',
                db='study_monitor', charset=charset
            )
            cur = await conn.cursor()
            
            # Update via raw SQL
            for sid in [5, 6, 7, 8]:
                await cur.execute(
                    'UPDATE grading_reports SET feedback = %s, generated_by = %s, detail = %s WHERE id = %s',
                    (FEEDBACK, GENERATED_BY, DETAIL, sid)
                )
            await conn.commit()
            print(f'Updated with charset={charset}')
            
            # Read back
            await cur.execute('SELECT id, feedback, generated_by FROM grading_reports WHERE id = 5')
            r = await cur.fetchone()
            print(f'Read back: id={r[0]}, feedback={r[1][:30]}..., by={r[2]}')
            
            # HEX check
            await cur.execute("SELECT HEX(feedback) FROM grading_reports WHERE id = 5")
            hex_val = await cur.fetchone()
            print(f'HEX (first 60 chars): {hex_val[0][:60] if hex_val else "NONE"}')
            
            await cur.close()
            await conn.ensure_closed()
        except Exception as e:
            print(f'Error with {charset}: {e}')

asyncio.run(main())
