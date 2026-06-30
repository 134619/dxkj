from typing import Any, Dict, List, Optional

import psycopg
from libenhance import get_cnf

# 字段映射配置
FIELD_MAPPING = {
    "ads_cost_j0014_fab8_processflow": {
        
    },
    "ads_cost_j0014_fab8_goodissue": {
        
    },
    "ads_cost_j0014_fab8_splitmergehistory": {
        
    },
    "ads_cost_j0014_fab8_workinprocess": {
        
    }
}


class PostgreSQL:
    def __init__(self):
        self.conn = psycopg.connect(
            host=get_cnf("pgsql.hostname"),
            port=get_cnf("pgsql.port"),
            dbname=get_cnf("pgsql.database"),
            user=get_cnf("pgsql.username"),
            password=get_cnf("pgsql.password")
        )
        self.conn.autocommit = False
        self.field_mapping = FIELD_MAPPING

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    def _convert_fields(self, data, table_name):
        """字段名转换"""
        if not data or table_name not in self.field_mapping:
            return data

        mapping = self.field_mapping[table_name]
        return {mapping.get(k, k): v for k, v in data.items()}

    def query(self, sql, table_name=None):
        """查询数据，传了table_name才转换字段"""
        with self.conn.cursor() as cur:
            cur.execute(sql)

            results = []
            for row in cur.fetchall():
                columns = [desc[0] for desc in cur.description]
                row_dict = dict(zip(columns, row))
                results.append(row_dict)

            if table_name:
                results = [self._convert_fields(row, table_name) for row in results]

            return results

    def execute(self, sql, params=None):
        """执行SQL"""
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
            self.conn.commit()
            return cur.rowcount


if __name__ == "__main__":
    db = PostgreSQL()

    data = db.query(f"""
    SELECT tablename 
    FROM pg_tables 
    WHERE schemaname = '{get_cnf("pgsql.schema")}'
    """)
    print(data)

    data = db.query(f"""
    select * from {get_cnf("pgsql.schema")}.ads_cost_j0014_fab8_splitmergehistory limit 1
    """, "ads_cost_j0014_fab8_splitmergehistory")

    print(data)
