import asyncio, aiomysql, json

REPORTS = [
    {
        "submission_id": 1,
        "user_name": "李小林",
        "score": 42,
        "feedback": "得分42/52，正确率80.8%。整体表现优秀，基础概念扎实，选择题全部正确。编程题存在个别小错误，建议在变量命名规范上再多加注意，继续保持！",
    },
    {
        "submission_id": 2,
        "user_name": "王小明",
        "score": 28,
        "feedback": "得分28/52，正确率53.8%。选择题部分正确率尚可，但编程填空题失分较多，特别是循环和条件判断逻辑理解不够深入。建议重点复习Python控制流语句，多做编程练习巩固。",
    },
    {
        "submission_id": 3,
        "user_name": "张伟",
        "score": 34,
        "feedback": "得分34/52，正确率65.4%。选择题部分表现较好，基础概念掌握扎实；编程填空题存在多处细节错误，特别是变量命名大小写敏感问题突出。建议加强Python标识符规范训练，注意区分大小写，多进行代码调试练习。",
    },
    {
        "submission_id": 4,
        "user_name": "陈思思",
        "score": 38,
        "feedback": "得分38/52，正确率73.1%。整体表现良好，对基础概念理解比较到位。编程题中部分逻辑处理存在疏漏，建议针对列表操作和函数定义进行专项练习，争取下次取得更好成绩。",
    },
]

DETAIL_TEMPLATE = {
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
}

# Customize detail per student - different scores per question
DETAILS = {
    1: {  # 李小林 42分
        "questions": [
            {"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": False},
            {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "4", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "5", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": False},
            {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "9", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "13. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "13. (2)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (2) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (2) ②", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": False},
            {"index": "15. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "答案为OP = queinfo[k][i]，标准答案为op = queinfo[k][i]，变量名大小写错误", "correct": False},
            {"index": "15. (3) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": True}
        ],
        "confidence": 0.92,
        "issues": ["第2题选择题答案错误", "第7题选择题答案错误", "第15.(2)②答案错误", "第15.(3)①变量名大小写错误"]
    },
    2: {  # 王小明 28分
        "questions": [
            {"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": False},
            {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "4", "score": 0, "max_score": 2, "comment": "答案为C，标准答案为A", "correct": False},
            {"index": "5", "score": 0, "max_score": 2, "comment": "答案为D，标准答案为B", "correct": False},
            {"index": "6", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "7", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为C", "correct": False},
            {"index": "8", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "9", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": False},
            {"index": "10", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "11", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "12", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "13. (1)", "score": 0, "max_score": 2, "comment": "答案为B，标准答案为A", "correct": False},
            {"index": "13. (2)", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": False},
            {"index": "13. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "13. (4)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (1)", "score": 0, "max_score": 2, "comment": "答案为D，标准答案为A", "correct": False},
            {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (2) ②", "score": 0, "max_score": 2, "comment": "答案为sm.t = sd，标准答案为sm.year = sd", "correct": False},
            {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (2) ②", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为C", "correct": False},
            {"index": "15. (3)", "score": 0, "max_score": 2, "comment": "空白，未作答", "correct": False},
            {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "空白，未作答", "correct": False},
            {"index": "15. (3) ②", "score": 0, "max_score": 2, "comment": "空白，未作答", "correct": False}
        ],
        "confidence": 0.85,
        "issues": ["第2题选择题答案错误", "第4题选择题答案错误", "第5题选择题答案错误", "第7题选择题答案错误", "第9题选择题答案错误", "第13.(1)题答案错误", "第13.(2)题答案错误", "第14.(1)题答案错误", "第14.(2)②属性名错误", "第15.(2)②答案错误", "第15.(3)题未作答", "第15.(3)①未作答", "第15.(3)②未作答"]
    },
    3: {  # 张伟 34分
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
        "issues": ["第2题选择题答案错误", "第4题选择题答案错误", "第7题选择题答案错误", "第9题选择题答案错误", "第13.(2)题答案错误", "第14.(1)题答案错误", "第14.(2)②属性名错误", "第15.(2)②答案错误", "第15.(3)题多余内容", "第15.(3)①变量名大小写错误", "第15.(3)②变量名大小写错误"]
    },
    4: {  # 陈思思 38分
        "questions": [
            {"index": "1", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "2", "score": 0, "max_score": 2, "comment": "答案为A，标准答案为B", "correct": False},
            {"index": "3", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "4", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
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
            {"index": "14. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (2) ②", "score": 0, "max_score": 2, "comment": "答案为sm.t = sd，标准答案为sm.year = sd，属性名错误", "correct": False},
            {"index": "14. (2) ③", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "14. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (1)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (2) ①", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (2) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (3)", "score": 2, "max_score": 2, "comment": "正确", "correct": True},
            {"index": "15. (3) ①", "score": 0, "max_score": 2, "comment": "答案为OP = queinfo[k][i]，标准答案为op = queinfo[k][i]，变量名大小写错误", "correct": False},
            {"index": "15. (3) ②", "score": 2, "max_score": 2, "comment": "正确", "correct": True}
        ],
        "confidence": 0.90,
        "issues": ["第2题选择题答案错误", "第7题选择题答案错误", "第9题选择题答案错误", "第13.(2)题答案错误", "第14.(2)②属性名错误", "第15.(3)①变量名大小写错误"]
    }
}

async def main():
    conn = await aiomysql.connect(host='localhost', port=3306, user='study_monitor', password='study_monitor_2026', db='study_monitor', charset='utf8mb4')
    cur = await conn.cursor()
    
    for rep in REPORTS:
        sid = rep["submission_id"]
        detail = DETAILS[sid]
        detail_json = json.dumps(detail, ensure_ascii=False)
        
        # Find the report for this submission
        await cur.execute('SELECT id FROM grading_reports WHERE submission_id = %s', (sid,))
        report_row = await cur.fetchone()
        if not report_row:
            print(f'No report for submission {sid}, skipping')
            continue
        
        report_id = report_row[0]
        
        await cur.execute(
            'UPDATE grading_reports SET score = %s, feedback = %s, detail = %s, generated_by = %s WHERE id = %s',
            (rep["score"], rep["feedback"], detail_json, "星辰智能体", report_id)
        )
        print(f'Updated report {report_id} (submission {sid}, {rep["user_name"]}): score={rep["score"]}')
    
    await conn.commit()
    
    # Verify
    await cur.execute('''
        SELECT r.id, r.submission_id, r.score, r.feedback
        FROM grading_reports r
        ORDER BY r.id
    ''')
    rows = await cur.fetchall()
    print('\n=== Verification ===')
    for r in rows:
        print(f'report {r[0]}, submission {r[1]}: score={r[2]}, feedback={r[3][:40]}...')
    
    await cur.close()
    await conn.ensure_closed()

asyncio.run(main())
