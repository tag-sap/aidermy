from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from .database import get_all_check_history, get_check_stats, get_connection, PRODUCTS_DB
import os

# Админка будет подключаться к основному app

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = "admin"
    correct_password = "aidermy2026"
    
    if credentials.username != correct_username or credentials.password != correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

def setup_admin_routes(app: FastAPI):
    """Регистрирует все админ-роуты в приложении"""
    
    @app.get("/admin", response_class=HTMLResponse)
    async def admin_panel(_: bool = Depends(verify_admin)):
        # Получаем данные
        history = get_all_check_history(limit=100)
        stats = get_check_stats()
        
        # Только проверки с составом (не нулевые)
        filtered_history = [h for h in history if h.get('score', 0) > 0]
        
        pending = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, u.email as user_email 
                FROM pending_products p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.status = 'pending'
                ORDER BY p.created_at DESC
                LIMIT 50
            ''')
            pending = cursor.fetchall()
            conn.close()
        except:
            pass
        
        # Получаем пользователей
        users = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, email, name, is_verified, created_at 
                FROM users 
                ORDER BY created_at DESC
                LIMIT 50
            ''')
            users = cursor.fetchall()
            conn.close()
        except:
            pass
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Aidermy Admin</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{ box-sizing: border-box; }}
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; flex-wrap: wrap; gap: 10px; }}
                h1 {{ color: #1a1a1a; font-size: 28px; margin: 0; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
                .stat-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
                .stat-card .number {{ font-size: 32px; font-weight: 700; color: #FF4F00; }}
                .stat-card .label {{ font-size: 14px; color: #666; margin-top: 4px; }}
                .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
                .tab-btn {{ padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; background: #e0e0e0; transition: 0.3s; }}
                .tab-btn.active {{ background: #FF4F00; color: white; }}
                .tab-btn:hover {{ opacity: 0.8; }}
                .tab-content {{ display: none; }}
                .tab-content.active {{ display: block; }}
                .table-wrap {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 30px; }}
                .table-header {{ padding: 16px 20px; background: #FFF3E0; border-bottom: 2px solid #FF4F00; font-weight: 600; color: #FF4F00; display: flex; justify-content: space-between; align-items: center; }}
                .bulk-actions {{ display: flex; gap: 8px; }}
                .btn-bulk-approve {{ background: #4CAF50; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }}
                .btn-bulk-reject {{ background: #f44336; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }}
                .btn-bulk-delete {{ background: #ff9800; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }}
                .btn-bulk-approve:hover, .btn-bulk-reject:hover, .btn-bulk-delete:hover {{ opacity: 0.8; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
                th {{ background: #FF4F00; color: white; padding: 12px 16px; text-align: left; font-weight: 600; }}
                td {{ padding: 12px 16px; border-bottom: 1px solid #eee; }}
                tr:hover {{ background: #f9f9f9; }}
                .badge {{ background: #FF4F00; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
                .badge-green {{ background: #4CAF50; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
                .badge-red {{ background: #f44336; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
                .btn-approve {{ background: #4CAF50; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; margin-right: 4px; font-size: 14px; }}
                .btn-approve:hover {{ opacity: 0.8; }}
                .btn-reject {{ background: #f44336; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
                .btn-reject:hover {{ opacity: 0.8; }}
                .btn-delete {{ background: #ff9800; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
                .btn-delete:hover {{ opacity: 0.8; }}
                .footer {{ text-align: center; color: #999; font-size: 13px; margin-top: 30px; }}
                .refresh-btn {{ background: #FF4F00; color: white; border: none; padding: 10px 24px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }}
                .refresh-btn:hover {{ opacity: 0.9; }}
                .empty-state {{ text-align: center; padding: 30px; color: #999; }}
                @media (max-width: 600px) {{ .stats-grid {{ grid-template-columns: 1fr 1fr; }} .table-wrap {{ overflow-x: auto; }} td, th {{ padding: 8px 10px; font-size: 12px; }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🧴 Aidermy Admin</h1>
                    <button class="refresh-btn" onclick="location.reload()">🔄 Обновить</button>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card"><div class="number">{stats['total']}</div><div class="label">📊 Всего проверок</div></div>
                    <div class="stat-card"><div class="number">{stats['unique_products']}</div><div class="label">🧴 Уникальных продуктов</div></div>
                    <div class="stat-card"><div class="number">{stats['avg_score']}</div><div class="label">⭐ Средний балл</div></div>
                </div>

                <!-- Вкладки -->
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('history')">📋 История ({len(filtered_history)})</button>
                    <button class="tab-btn" onclick="switchTab('moderation')">📦 Модерация ({len(pending)})</button>
                    <button class="tab-btn" onclick="switchTab('users')">👤 Пользователи ({len(users)})</button>
                </div>

                <!-- Вкладка: История -->
                <div id="tab-history" class="tab-content active">
                    <div class="table-wrap">
                        <div class="table-header"><span>📋 История проверок</span></div>
                        <table>
                            <thead><tr><th>ID</th><th>Продукт</th><th>Тип кожи</th><th>Оценка</th><th>Вердикт</th><th>Резюме</th><th>Дата</th></tr></thead>
                            <tbody>
        """
        
        if filtered_history:
            for row in filtered_history[:50]:
                html += f"""
                                <tr>
                                    <td>{row['id']}</td>
                                    <td><strong>{row['product_name']}</strong></td>
                                    <td>{row['skin_type']}</td>
                                    <td><span class="badge">{row['score']}%</span></td>
                                    <td>{row['verdict']}</td>
                                    <td style="font-size: 12px; max-width: 250px; word-break: break-word;">{row['summary'][:60]}{'...' if len(row['summary']) > 60 else ''}</td>
                                    <td style="font-size: 12px;">{row['created_at']}</td>
                                </tr>
                """
        else:
            html += """<tr><td colspan="7" class="empty-state">📭 Нет проверок с составом</td></tr>"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Вкладка: Модерация -->
                <div id="tab-moderation" class="tab-content">
                    <div class="table-wrap">
                        <div class="table-header">
                            <span>📦 Продукты на модерацию ({len(pending)})</span>
                            <div class="bulk-actions">
                                <button class="btn-bulk-approve" onclick="bulkAction('approve')">✅ Одобрить выбранные</button>
                                <button class="btn-bulk-reject" onclick="bulkAction('reject')">❌ Отклонить выбранные</button>
                                <button class="btn-bulk-delete" onclick="bulkAction('delete')">🗑️ Удалить выбранные</button>
                            </div>
                        </div>
                        <table>
                            <thead>
                                <tr>
                                    <th><input type="checkbox" id="select-all" onchange="toggleAll(this.checked)"></th>
                                    <th>ID</th>
                                    <th>Название</th>
                                    <th>Состав</th>
                                    <th>Отправил</th>
                                    <th>Дата</th>
                                    <th>Действия</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        if pending:
            for p in pending:
                row = dict(p)
                user_email = row.get('user_email', 'Аноним')
                html += f"""
                                <tr>
                                    <td><input type="checkbox" class="product-checkbox" value="{row['id']}"></td>
                                    <td>{row['id']}</td>
                                    <td><strong>{row['product_name']}</strong></td>
                                    <td style="font-size: 12px; max-width: 200px; word-break: break-word;">{row['ingredients'][:80]}{'...' if len(row['ingredients']) > 80 else ''}</td>
                                    <td>{user_email}</td>
                                    <td style="font-size: 12px;">{row['created_at']}</td>
                                    <td>
                                        <button class="btn-approve" onclick="approve({row['id']})">✅</button>
                                        <button class="btn-reject" onclick="reject({row['id']})">❌</button>
                                        <button class="btn-delete" onclick="deleteProduct({row['id']})">🗑️</button>
                                    </td>
                                </tr>
                """
        else:
            html += """<tr><td colspan="7" class="empty-state">🎉 Нет продуктов на модерацию</td></tr>"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Вкладка: Пользователи -->
                <div id="tab-users" class="tab-content">
                    <div class="table-wrap">
                        <div class="table-header"><span>👤 Зарегистрированные пользователи ({len(users)})</span></div>
                        <table>
                            <thead><tr><th>ID</th><th>Email</th><th>Имя</th><th>Верифицирован</th><th>Дата регистрации</th></tr></thead>
                            <tbody>
        """
        
        if users:
            for u in users:
                row = dict(u)
                verified_badge = '<span class="badge-green">✅ Да</span>' if row.get('is_verified') else '<span class="badge-red">❌ Нет</span>'
                html += f"""
                                <tr>
                                    <td>{row['id']}</td>
                                    <td><strong>{row['email']}</strong></td>
                                    <td>{row.get('name', '—')}</td>
                                    <td>{verified_badge}</td>
                                    <td style="font-size: 12px;">{row['created_at']}</td>
                                </tr>
                """
        else:
            html += """<tr><td colspan="5" class="empty-state">👤 Нет зарегистрированных пользователей</td></tr>"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <div class="footer"><p>🟢 База данных работает</p></div>
            </div>

            <script>
            function switchTab(tab) {
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                document.getElementById('tab-' + tab).classList.add('active');
                document.querySelector(`.tab-btn[onclick="switchTab('${tab}')"]`).classList.add('active');
            }
            
            function toggleAll(checked) {
                document.querySelectorAll('.product-checkbox').forEach(cb => cb.checked = checked);
            }

            function getSelectedIds() {
                return Array.from(document.querySelectorAll('.product-checkbox:checked')).map(cb => cb.value);
            }

            async function bulkAction(action) {
                const ids = getSelectedIds();
                if (ids.length === 0) {
                    alert('Выберите хотя бы один продукт');
                    return;
                }
                
                const messages = {
                    'approve': 'Одобрить выбранные продукты?',
                    'reject': 'Отклонить выбранные продукты?',
                    'delete': 'Удалить выбранные продукты?'
                };
                
                if (!confirm(messages[action])) return;
                
                const endpoints = {
                    'approve': '/api/admin/bulk-approve',
                    'reject': '/api/admin/bulk-reject',
                    'delete': '/api/admin/bulk-delete'
                };
                
                try {
                    const response = await fetch(endpoints[action], {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ids: ids})
                    });
                    const data = await response.json();
                    alert(data.message);
                    location.reload();
                } catch (error) {
                    alert('Ошибка: ' + error.message);
                }
            }
            
            function approve(id) {
                if (!confirm('Одобрить этот продукт?')) return;
                fetch('/api/admin/approve-product/' + id, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => { alert(data.message || '✅ Одобрено!'); location.reload(); })
                    .catch(() => alert('Ошибка'));
            }
            function reject(id) {
                if (!confirm('Отклонить этот продукт?')) return;
                fetch('/api/admin/reject-product/' + id, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => { alert(data.message || '❌ Отклонено!'); location.reload(); })
                    .catch(() => alert('Ошибка'));
            }
            function deleteProduct(id) {
                if (!confirm('🗑️ Удалить этот продукт навсегда?')) return;
                fetch('/api/admin/delete-product/' + id, { method: 'DELETE' })
                    .then(r => r.json())
                    .then(data => { alert(data.message || '🗑️ Удалено!'); location.reload(); })
                    .catch(() => alert('Ошибка'));
            }
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html)

    # === АДМИН: ЭНДПОИНТЫ С BASIC AUTH ===
    @app.get("/api/admin/pending-products")
    async def get_pending_products(_: bool = Depends(verify_admin)):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, u.email as user_email 
            FROM pending_products p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.status = 'pending'
            ORDER BY p.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return {"products": [dict(row) for row in rows]}

    @app.post("/api/admin/bulk-approve")
    async def bulk_approve(request: Request, _: bool = Depends(verify_admin)):
        """Массовое одобрение продуктов"""
        data = await request.json()
        product_ids = data.get('ids', [])
        
        if not product_ids:
            raise HTTPException(status_code=400, detail="Нет IDs для обработки")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        approved_count = 0
        for product_id in product_ids:
            cursor.execute("SELECT * FROM pending_products WHERE id = ? AND status = 'pending'", (product_id,))
            pending = cursor.fetchone()
            
            if pending:
                conn_products = get_connection(PRODUCTS_DB)
                cursor_products = conn_products.cursor()
                cursor_products.execute('''
                    INSERT INTO products (name, ingredients, slug, saved_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (pending['product_name'], pending['ingredients'], pending['slug']))
                conn_products.commit()
                conn_products.close()
                
                cursor.execute('''
                    UPDATE pending_products 
                    SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (product_id,))
                approved_count += 1
        
        conn.commit()
        conn.close()
        
        return {"message": f"✅ Одобрено {approved_count} продуктов"}

    @app.post("/api/admin/bulk-reject")
    async def bulk_reject(request: Request, _: bool = Depends(verify_admin)):
        """Массовое отклонение продуктов"""
        data = await request.json()
        product_ids = data.get('ids', [])
        
        if not product_ids:
            raise HTTPException(status_code=400, detail="Нет IDs для обработки")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        rejected_count = 0
        for product_id in product_ids:
            cursor.execute('''
                UPDATE pending_products 
                SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'
            ''', (product_id,))
            if cursor.rowcount > 0:
                rejected_count += 1
        
        conn.commit()
        conn.close()
        
        return {"message": f"❌ Отклонено {rejected_count} продуктов"}

    @app.post("/api/admin/bulk-delete")
    async def bulk_delete(request: Request, _: bool = Depends(verify_admin)):
        """Массовое удаление продуктов"""
        data = await request.json()
        product_ids = data.get('ids', [])
        
        if not product_ids:
            raise HTTPException(status_code=400, detail="Нет IDs для обработки")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        deleted_count = 0
        for product_id in product_ids:
            cursor.execute("DELETE FROM pending_products WHERE id = ?", (product_id,))
            if cursor.rowcount > 0:
                deleted_count += 1
        
        conn.commit()
        conn.close()
        
        return {"message": f"🗑️ Удалено {deleted_count} продуктов"}

    @app.post("/api/admin/approve-product/{product_id}")
    async def approve_product(product_id: int, _: bool = Depends(verify_admin)):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_products WHERE id = ? AND status = 'pending'", (product_id,))
        pending = cursor.fetchone()
        
        if not pending:
            conn.close()
            raise HTTPException(status_code=404, detail="Продукт не найден или уже обработан")
        
        conn_products = get_connection(PRODUCTS_DB)
        cursor_products = conn_products.cursor()
        cursor_products.execute('''
            INSERT INTO products (name, ingredients, slug, saved_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (pending['product_name'], pending['ingredients'], pending['slug']))
        conn_products.commit()
        conn_products.close()
        
        cursor.execute('''
            UPDATE pending_products 
            SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (product_id,))
        conn.commit()
        conn.close()
        
        return {"message": "Продукт одобрен и добавлен в базу! ✅"}

    @app.post("/api/admin/reject-product/{product_id}")
    async def reject_product(product_id: int, _: bool = Depends(verify_admin)):
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pending_products 
            SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (product_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Продукт не найден")
        
        conn.commit()
        conn.close()
        
        return {"message": "Продукт отклонён ❌"}

    @app.delete("/api/admin/delete-product/{product_id}")
    async def delete_product(product_id: int, _: bool = Depends(verify_admin)):
        # Проверяем в pending
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_products WHERE id = ?", (product_id,))
        pending = cursor.fetchone()
        
        if pending:
            cursor.execute("DELETE FROM pending_products WHERE id = ?", (product_id,))
            conn.commit()
            conn.close()
            return {"message": "Продукт удалён из модерации 🗑️"}
        
        conn.close()
        
        # Проверяем в основной базе
        conn_products = get_connection(PRODUCTS_DB)
        cursor_products = conn_products.cursor()
        cursor_products.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor_products.fetchone()
        
        if product:
            cursor_products.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn_products.commit()
            conn_products.close()
            return {"message": "Продукт удалён из базы 🗑️"}
        
        conn_products.close()
        
        raise HTTPException(status_code=404, detail="Продукт не найден")