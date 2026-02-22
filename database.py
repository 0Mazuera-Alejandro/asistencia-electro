import sqlite3
from datetime import datetime
import os

class DatabaseManager:
    def __init__(self, db_name="asistencia.db"):
        self.db_name = db_name
        self.init_database()
    
    def get_connection(self):
        """Crea conexión a la base de datos con timeout"""
        conn = sqlite3.connect(self.db_name, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")  # Mejora concurrencia
        return conn
    
    def init_database(self):
        """Inicializa las tablas de la base de datos"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Tabla de estudiantes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS estudiantes (
                codigo TEXT PRIMARY KEY,
                numero_programa TEXT NOT NULL,
                nombre_programa TEXT NOT NULL,
                nombre_completo TEXT NOT NULL,
                email TEXT NOT NULL,
                fecha_registro TEXT NOT NULL
            )
        ''')
        
        # Tabla de asistencias CON JORNADA
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asistencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_estudiante TEXT NOT NULL,
                fecha_hora TEXT NOT NULL,
                jornada TEXT NOT NULL,
                FOREIGN KEY (codigo_estudiante) REFERENCES estudiantes(codigo)
            )
        ''')
        
        # Tabla de visitantes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS visitantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_completo TEXT NOT NULL,
                motivo TEXT NOT NULL,
                nombre_colegio TEXT,
                fecha_hora TEXT NOT NULL,
                jornada TEXT NOT NULL
            )
        ''')
        
        # MIGRACIÓN: Agregar columna jornada si no existe
        cursor.execute("PRAGMA table_info(asistencias)")
        columnas = [col[1] for col in cursor.fetchall()]
        
        if 'jornada' not in columnas:
            print("Agregando columna 'jornada' a asistencias existentes...")
            cursor.execute('ALTER TABLE asistencias ADD COLUMN jornada TEXT DEFAULT "Mañana"')
            
            # Actualizar jornadas de registros antiguos basándose en la hora
            cursor.execute('SELECT id, fecha_hora FROM asistencias')
            registros = cursor.fetchall()
            
            for reg_id, fecha_hora in registros:
                try:
                    hora = int(fecha_hora.split()[1].split(':')[0])
                    if 6 <= hora < 12:
                        jornada = "Mañana"
                    elif 12 <= hora < 18:
                        jornada = "Tarde"
                    else:
                        jornada = "Noche"
                    
                    cursor.execute('UPDATE asistencias SET jornada = ? WHERE id = ?', (jornada, reg_id))
                except:
                    pass
            
            print("Migración completada.")
        
        conn.commit()
        conn.close()
    
    def determinar_jornada(self, hora):
        """Determina la jornada según la hora"""
        if 6 <= hora < 12:
            return "Mañana"
        elif 12 <= hora < 18:
            return "Tarde"
        elif 18 <= hora <= 21:
            return "Noche"
        else:
            return None
    
    def obtener_estadisticas_por_programa(self, anio=None, mes_inicio=None, mes_fin=None):
        """Obtiene cantidad de asistencias por programa con filtros opcionales"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT e.nombre_programa, COUNT(*) as total
            FROM asistencias a
            JOIN estudiantes e ON a.codigo_estudiante = e.codigo
        '''
        
        conditions = []
        params = []
        
        if anio and anio != "Todos":
            conditions.append("strftime('%Y', a.fecha_hora) = ?")
            params.append(str(anio))
        
        if mes_inicio and mes_fin:
            conditions.append("CAST(strftime('%m', a.fecha_hora) AS INTEGER) BETWEEN ? AND ?")
            params.extend([mes_inicio, mes_fin])
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += '''
            GROUP BY e.nombre_programa
            ORDER BY total DESC
        '''
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        conn.close()
        return resultados
    
    def obtener_asistencias_por_horario(self, anio=None, mes_inicio=None, mes_fin=None):
        """Obtiene asistencias agrupadas por horario con filtros opcionales"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = '''
            SELECT jornada, COUNT(*) as total
            FROM asistencias
        '''
        
        conditions = []
        params = []
        
        if anio and anio != "Todos":
            conditions.append("strftime('%Y', fecha_hora) = ?")
            params.append(str(anio))
        
        if mes_inicio and mes_fin:
            conditions.append("CAST(strftime('%m', fecha_hora) AS INTEGER) BETWEEN ? AND ?")
            params.extend([mes_inicio, mes_fin])
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += '''
            GROUP BY jornada
            ORDER BY 
                CASE jornada
                    WHEN 'Mañana' THEN 1
                    WHEN 'Tarde' THEN 2
                    WHEN 'Noche' THEN 3
                    WHEN 'Fuera de horario' THEN 3
                END
        '''
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        # Combinar "Fuera de horario" con "Noche"
        jornadas_dict = {}
        for jornada, total in resultados:
            if jornada == "Fuera de horario":
                jornada = "Noche"
            
            if jornada in jornadas_dict:
                jornadas_dict[jornada] += total
            else:
                jornadas_dict[jornada] = total
        
        conn.close()
        return [(jornada, total) for jornada, total in jornadas_dict.items()]
    
    def obtener_asistencias_por_mes(self, anio=None, mes_inicio=None, mes_fin=None):
        """Obtiene asistencias por mes con filtros opcionales"""
        if anio is None:
            anio = datetime.now().year
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if anio == "Todos":
            # Para "Todos", agrupar por año y mes
            query = '''
                SELECT strftime('%Y-%m', fecha_hora) as anio_mes, COUNT(*) as total
                FROM asistencias
            '''
            params = []
        else:
            query = '''
                SELECT strftime('%m', fecha_hora) as mes, COUNT(*) as total
                FROM asistencias
                WHERE strftime('%Y', fecha_hora) = ?
            '''
            params = [str(anio)]
        
        if mes_inicio and mes_fin and anio != "Todos":
            query += " AND CAST(strftime('%m', fecha_hora) AS INTEGER) BETWEEN ? AND ?"
            params.extend([mes_inicio, mes_fin])
        
        query += '''
            GROUP BY {}
            ORDER BY {}
        '''.format(
            'anio_mes' if anio == "Todos" else 'mes',
            'anio_mes' if anio == "Todos" else 'mes'
        )
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        conn.close()
        
        if anio == "Todos":
            # Devolver tal cual para "Todos"
            return resultados
        
        # Determinar rango de meses a mostrar
        inicio = mes_inicio if mes_inicio else 1
        fin = mes_fin if mes_fin else 12
        
        # Crear diccionario con los meses del rango
        meses_dict = {f"{i:02d}": 0 for i in range(inicio, fin + 1)}
        for mes, total in resultados:
            if mes in meses_dict:
                meses_dict[mes] = total
        
        return [(mes, total) for mes, total in meses_dict.items()]
    
    def agregar_estudiante(self, codigo, numero_programa, nombre_programa, nombre_completo, email):
        """Agrega un nuevo estudiante a la base de datos"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            fecha_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute('''
                INSERT INTO estudiantes (codigo, numero_programa, nombre_programa, nombre_completo, email, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (codigo, numero_programa, nombre_programa, nombre_completo, email, fecha_registro))
            
            conn.commit()
            conn.close()
            return True, "Estudiante agregado exitosamente"
        except sqlite3.IntegrityError:
            return False, "El código ya existe en la base de datos"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def agregar_estudiantes_lote(self, lista_estudiantes):
        """Agrega múltiples estudiantes en una sola transacción (más rápido)"""
        exitosos = 0
        duplicados = 0
        errores = []
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        fecha_registro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for estudiante in lista_estudiantes:
            try:
                cursor.execute('''
                    INSERT INTO estudiantes (codigo, numero_programa, nombre_programa, nombre_completo, email, fecha_registro)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (estudiante['codigo'], estudiante['numero_programa'], 
                      estudiante['nombre_programa'], estudiante['nombre_completo'],
                      estudiante['email'], fecha_registro))
                exitosos += 1
            except sqlite3.IntegrityError:
                duplicados += 1
            except Exception as e:
                errores.append(f"{estudiante['codigo']}: {str(e)}")
        
        conn.commit()
        conn.close()
        
        return exitosos, duplicados, errores
    
    def buscar_estudiante(self, codigo):
        """Busca un estudiante por su código"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT codigo, numero_programa, nombre_programa, nombre_completo, email, fecha_registro
            FROM estudiantes
            WHERE codigo = ?
        ''', (codigo,))
        
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado:
            return {
                'codigo': resultado[0],
                'numero_programa': resultado[1],
                'nombre_programa': resultado[2],
                'nombre_completo': resultado[3],
                'email': resultado[4],
                'fecha_registro': resultado[5]
            }
        return None
    
    def obtener_todos_estudiantes(self):
        """Obtiene todos los estudiantes registrados"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT codigo, numero_programa, nombre_programa, nombre_completo, email, fecha_registro
            FROM estudiantes
            ORDER BY datetime(fecha_registro) DESC
        ''')
        
        resultados = cursor.fetchall()
        conn.close()
        
        return resultados
    
    def eliminar_estudiante(self, codigo):
        """Elimina un estudiante y todas sus asistencias"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Eliminar asistencias del estudiante
            cursor.execute('DELETE FROM asistencias WHERE codigo_estudiante = ?', (codigo,))
            
            # Eliminar estudiante
            cursor.execute('DELETE FROM estudiantes WHERE codigo = ?', (codigo,))
            
            conn.commit()
            conn.close()
            return True, "Estudiante eliminado exitosamente"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def actualizar_estudiante(self, codigo, numero_programa, nombre_programa, nombre_completo, email):
        """Actualiza la información de un estudiante"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE estudiantes
                SET numero_programa = ?, nombre_programa = ?, nombre_completo = ?, email = ?
                WHERE codigo = ?
            ''', (numero_programa, nombre_programa, nombre_completo, email, codigo))
            
            conn.commit()
            conn.close()
            return True, "Estudiante actualizado exitosamente"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def registrar_asistencia(self, codigo_estudiante):
        """Registra la asistencia de un estudiante - UNA VEZ POR JORNADA"""
        try:
            ahora = datetime.now()
            hora_actual = ahora.hour
            minuto_actual = ahora.minute
            
            # Determinar jornada actual
            jornada_actual = self.determinar_jornada(hora_actual)
            
            if jornada_actual is None:
                if hora_actual < 6:
                    return False, "El laboratorio aún no ha abierto. Abre a las 6:00 AM"
                else:
                    return False, "El laboratorio ya cerró. Cierra a las 9:00 PM"
            
            # Nombres descriptivos de jornadas
            jornadas_info = {
                "Mañana": "6:00 AM - 11:59 AM",
                "Tarde": "12:00 PM - 5:59 PM",
                "Noche": "6:00 PM - 9:00 PM"
            }
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Verificar si ya registró en esta jornada HOY
            fecha_hoy = ahora.strftime("%Y-%m-%d")
            
            cursor.execute('''
                SELECT COUNT(*) FROM asistencias
                WHERE codigo_estudiante = ?
                AND DATE(fecha_hora) = ?
                AND jornada = ?
            ''', (codigo_estudiante, fecha_hoy, jornada_actual))
            
            ya_registro = cursor.fetchone()[0]
            
            if ya_registro > 0:
                conn.close()
                return False, f"Ya registraste asistencia en la jornada de {jornada_actual} ({jornadas_info[jornada_actual]}) hoy"
            
            # Si no ha registrado en esta jornada, proceder
            fecha_hora = ahora.strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute('''
                INSERT INTO asistencias (codigo_estudiante, fecha_hora, jornada)
                VALUES (?, ?, ?)
            ''', (codigo_estudiante, fecha_hora, jornada_actual))
            
            conn.commit()
            conn.close()
            return True, fecha_hora
            
        except Exception as e:
            return False, str(e)
    
    def obtener_todas_asistencias(self):
        """Obtiene todas las asistencias registradas ordenadas por fecha correctamente"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.id, a.fecha_hora, e.codigo, e.email, e.nombre_programa, e.numero_programa
            FROM asistencias a
            JOIN estudiantes e ON a.codigo_estudiante = e.codigo
            ORDER BY datetime(a.fecha_hora) DESC
        ''')
        
        resultados = cursor.fetchall()
        conn.close()
        
        return resultados
    
    def obtener_asistencias_por_fecha(self, fecha_inicio, fecha_fin):
        """Obtiene asistencias en un rango de fechas"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.fecha_hora, e.codigo, e.nombre_completo, e.nombre_programa
            FROM asistencias a
            JOIN estudiantes e ON a.codigo_estudiante = e.codigo
            WHERE date(a.fecha_hora) BETWEEN ? AND ?
            ORDER BY a.fecha_hora DESC
        ''', (fecha_inicio, fecha_fin))
        
        resultados = cursor.fetchall()
        conn.close()
        
        return resultados
    
    def obtener_estadisticas(self):
        """Obtiene estadísticas generales"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total estudiantes registrados
        cursor.execute('SELECT COUNT(*) FROM estudiantes')
        total_estudiantes = cursor.fetchone()[0]
        
        # Total asistencias
        cursor.execute('SELECT COUNT(*) FROM asistencias')
        total_asistencias = cursor.fetchone()[0]
        
        # Asistencias hoy
        hoy = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('SELECT COUNT(*) FROM asistencias WHERE date(fecha_hora) = ?', (hoy,))
        asistencias_hoy = cursor.fetchone()[0]
        
        # Programa con más asistencias
        cursor.execute('''
            SELECT e.nombre_programa, COUNT(*) as total
            FROM asistencias a
            JOIN estudiantes e ON a.codigo_estudiante = e.codigo
            GROUP BY e.nombre_programa
            ORDER BY total DESC
            LIMIT 1
        ''')
        programa_top = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_estudiantes': total_estudiantes,
            'total_asistencias': total_asistencias,
            'asistencias_hoy': asistencias_hoy,
            'programa_top': programa_top if programa_top else ("N/A", 0)
        }
    def registrar_visitante(self, nombre_completo, motivo, nombre_colegio):
        """Registra un visitante en el sistema"""
        try:
            ahora = datetime.now()
            hora_actual = ahora.hour
            
            # Determinar jornada
            jornada = self.determinar_jornada(hora_actual)
            
            if jornada is None:
                if hora_actual < 6:
                    return False, "El laboratorio aún no ha abierto. Abre a las 6:00 AM"
                else:
                    return False, "El laboratorio ya cerró. Cierra a las 9:00 PM"
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            fecha_hora = ahora.strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute('''
                INSERT INTO visitantes (nombre_completo, motivo, nombre_colegio, fecha_hora, jornada)
                VALUES (?, ?, ?, ?, ?)
            ''', (nombre_completo, motivo, nombre_colegio, fecha_hora, jornada))
            
            conn.commit()
            conn.close()
            return True, fecha_hora
            
        except Exception as e:
            return False, str(e)

    def obtener_todos_visitantes(self):
        """Obtiene todos los visitantes registrados (más reciente primero)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, nombre_completo, motivo, nombre_colegio, fecha_hora, jornada
            FROM visitantes
            ORDER BY datetime(fecha_hora) DESC
        ''')
        
        resultados = cursor.fetchall()
        conn.close()
        
        return resultados
