import asyncio, aiomysql, json

async def main():
    conn = await aiomysql.connect(host='localhost', port=3306, user='study_monitor', password='study_monitor_2026', db='study_monitor', charset='utf8mb4')
    cur = await conn.cursor()
    
    # Check charset of the feedback column
    await cur.execute("""
        SELECT CCSA.character_set_name, CCSA.collation_name 
        FROM information_schema.COLUMNS CCSA 
        WHERE CCSA.table_schema = DATABASE() 
          AND CCSA.table_name = 'grading_reports'
          AND CCSA.column_name = 'feedback'
    """)
    row = await cur.fetchone()
    print(f'feedback column: charset={row[0]}, collation={row[1]}')
    
    # Check actual stored data
    await cur.execute('SELECT id, score, feedback, generated_by FROM grading_reports ORDER BY id')
    rows = await cur.fetchall()
    for r in rows:
        print(f'Report {r[0]}: score={r[1]}, feedback={repr(r[2])}, by={repr(r[3])}')
    
    # Try fetching via utf8mb4
    print("\n--- Raw bytes check ---")
    await cur.execute("SELECT HEX(feedback) FROM grading_reports WHERE id = 1")
    row = await cur.fetchone()
    print(f'HEX of feedback (id=1): {row[0]}')
    
    await cur.close()
    await conn.ensure_closed()

asyncio.run(main())
