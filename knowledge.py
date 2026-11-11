"""Project-scoped evidence from files, notes, tasks and approved memories."""
import sqlite3

import retrieval


def search(conn: sqlite3.Connection, query: str, limit: int = 8, project_id: str = '') -> list[dict]:
    results = retrieval.search_chunks(conn, query, limit, project_id=project_id)
    for item in results:
        item.update(item_type='source', item_id=item['source_id'])
    if not query.strip():
        return results
    terms = retrieval.latin_tokens(query)
    grams = set(retrieval._informative_bigrams(query))
    extra = []
    for kind, table, body, condition in (
        ('note', 'notes', 'body', '1=1'),
        ('task', 'tasks', 'title', '1=1'),
        ('memory', 'memories', 'body', "status = 'approved'"),
    ):
        sql = f'SELECT * FROM {table} WHERE {condition}'
        params = []
        if project_id:
            sql += ' AND id IN (SELECT item_id FROM collection_items WHERE collection_id=? AND item_type=?)'
            params = [project_id, kind]
        for row in conn.execute(sql, params):
            text = row[body]
            content = row['title'] + '\n' + text if body != 'title' else text
            hits = [t for t in terms if t in content.lower()]
            matched = sum(g in content for g in grams)
            if not hits and not matched and query not in content:
                continue
            coverage = retrieval._coverage(conn, query, content)
            score = (len(hits) + matched) / max(1, len(terms) + len(grams))
            extra.append({
                'item_type': kind, 'item_id': row['id'], 'source_id': '',
                'chunk_id': f'{kind}:{row["id"]}', 'chunk_index': 0,
                'title': row['title'], 'content': content, 'kind': kind,
                'page_start': 0, 'page_end': 0,
                'snippet': retrieval._snippet(content, list(grams), terms),
                'rank': score, 'confidence_signals': {
                    'coverage': coverage, 'latin_hits': hits, 'source': kind,
                },
            })
    extra.sort(key=lambda x: x['rank'], reverse=True)
    for i, item in enumerate(extra):
        item['rank'] = 2.0 / (retrieval.RRF_K + i + 1)
    return sorted(results + extra, key=lambda x: x['rank'], reverse=True)[:limit]


def select_source(conn: sqlite3.Connection, project_id: str, source_id: str, original_name: str) -> None:
    """Move only this project's document head; shared references stay active."""
    old = conn.execute(
        'SELECT source_id FROM source_heads WHERE project_id=? AND original_name=?',
        (project_id, original_name),
    ).fetchone()
    conn.execute(
        'INSERT INTO source_heads(project_id,original_name,source_id) VALUES (?,?,?) '
        'ON CONFLICT(project_id,original_name) DO UPDATE SET source_id=excluded.source_id',
        (project_id, original_name, source_id),
    )
    conn.execute("UPDATE sources SET superseded=0, superseded_by='' WHERE id=?", (source_id,))
    if old and old['source_id'] != source_id:
        conn.execute(
            'UPDATE sources SET superseded=1, superseded_by=? WHERE id=? '
            'AND NOT EXISTS (SELECT 1 FROM source_heads WHERE source_id=?)',
            (source_id, old['source_id'], old['source_id']),
        )
