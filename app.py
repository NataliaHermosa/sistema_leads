import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import plotly.express as px
import io
import base64
from PIL import Image
import os
from datetime import datetime
import hashlib
import time

# ============================================================================
# 1. CONFIGURAÇÃO, TEMA E CREDENCIAIS
# ============================================================================
st.set_page_config(
    page_title="Gestão de Leads | Gov Academy", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# Inicializar session_state PARA LOGIN E OUTROS ESTADOS 
if 'authenticated' not in st.session_state:  
    st.session_state.authenticated = False    
if 'user_info' not in st.session_state:         
    st.session_state.user_info = {}           
if 'opcoes' not in st.session_state:
    st.session_state.opcoes = {'cidades': {}}
if 'menu_atual' not in st.session_state:
    st.session_state.menu_atual = "Dashboard"
if 'search_term' not in st.session_state:
    st.session_state.search_term = ""
if 'login_attempts' not in st.session_state:  
    st.session_state.login_attempts = 0
if 'last_attempt_time' not in st.session_state: 
    st.session_state.last_attempt_time = 0


# ================================================
# 2. CONSTANTES E CONFIGURAÇÕES
# ================================================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = "1uZmmdxe1kqlBoOWsx9ghv2xNWLSBqncNiB47MP0qoAU"

# Cores
PRIMARY_COLOR = "#522b7b"
BG_COLOR = "#F0F4FF"
LOGO_HEIGHT = 80

# ============================================================================
# 3. FUNÇÕES DE AUTENTICAÇÃO E LOGIN (ADICIONAR ESTA SEÇÃO INTEIRA)
# ============================================================================
def hash_password(password):
    """Gera hash SHA-256 da senha"""
    return hashlib.sha256(password.encode()).hexdigest()

def validate_cpf(cpf):
    """Valida e formata CPF"""
    # Remove caracteres não numéricos
    cpf = ''.join(filter(str.isdigit, cpf))
    
    # Verifica se tem 11 dígitos
    if len(cpf) != 11:
        return False, "CPF deve conter 11 dígitos"
    
    # Formata CPF para exibição
    cpf_formatado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    
    return True, cpf_formatado

def check_login_attempts():
    """Verifica se há muitas tentativas de login"""
    current_time = time.time()
    
    # Reseta tentativas se passaram 5 minutos
    if current_time - st.session_state.last_attempt_time > 300:  # 5 minutos
        st.session_state.login_attempts = 0
    
    # Bloqueia após 5 tentativas
    if st.session_state.login_attempts >= 5:
        time_left = 300 - (current_time - st.session_state.last_attempt_time)
        if time_left > 0:
            minutes = int(time_left // 60)
            seconds = int(time_left % 60)
            return False, f"Muitas tentativas de login. Aguarde {minutes}:{seconds:02d} minutos."
    
    return True, ""

def verify_credentials(cpf, password):
    """Verifica credenciais no Google Sheets"""
    try:
        # Validar CPF
        valid, cpf_formatted = validate_cpf(cpf)
        if not valid:
            return False, cpf_formatted, None
        
        # Carregar dados de usuários
        creds = get_credentials()
        if not creds:
            return False, "Erro nas credenciais do sistema", None
        
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        
        # Tentar ler da aba 'usuarios' (se existir)
        try:
            worksheet = planilha.worksheet('usuarios')
            dados = worksheet.get_all_values()
            
            if dados and len(dados) > 1:
                df_usuarios = pd.DataFrame(dados[1:], columns=dados[0])
                
                # Verificar se há colunas necessárias
                colunas_needed = ['cpf', 'senha_hash', 'nome', 'nivel_acesso', 'ativo']
                for col in colunas_needed:
                    if col not in df_usuarios.columns:
                        # Tentar encontrar por nome similar
                        for actual_col in df_usuarios.columns:
                            if col in actual_col.lower():
                                df_usuarios.rename(columns={actual_col: col}, inplace=True)
                                break
                
                # Procurar usuário
                for _, user in df_usuarios.iterrows():
                    user_cpf = str(user.get('cpf', '')).strip()
                    
                    # Limpar CPF para comparação
                    user_cpf_clean = ''.join(filter(str.isdigit, user_cpf))
                    input_cpf_clean = ''.join(filter(str.isdigit, cpf))
                    
                    if user_cpf_clean == input_cpf_clean:
                        # Verificar se usuário está ativo
                        ativo = str(user.get('ativo', '')).strip().upper()
                        if ativo in ['NÃO', 'NAO', 'FALSE', '0', 'INATIVO']:
                            return False, "Usuário inativo. Contate o administrador.", None
                        
                        # Verificar senha
                        senha_hash_armazenada = str(user.get('senha_hash', '')).strip()
                        senha_hash_input = hash_password(password)
                        
                        if senha_hash_armazenada == senha_hash_input:
                            # Login bem-sucedido
                            user_info = {
                                'cpf': cpf_formatted,
                                'nome': user.get('nome', 'Usuário'),
                                'nivel_acesso': user.get('nivel_acesso', 'usuario'),
                                'email': user.get('email', ''),
                                'telefone': user.get('telefone', '')
                            }
                            return True, "Login realizado com sucesso!", user_info
                        else:
                            return False, "Senha incorreta", None
                
                return False, "CPF não encontrado", None
                
            else:
                # Se não há usuários cadastrados, criar usuário admin padrão
                return create_default_admin(cpf_formatted, password)
                
        except gspread.exceptions.WorksheetNotFound:
            # Se a aba 'usuarios' não existe, criar usuário admin padrão
            return create_default_admin(cpf_formatted, password)
            
    except Exception as e:
        return False, f"Erro no sistema: {str(e)}", None

def create_default_admin(cpf, password):
    """Cria usuário admin padrão se não existir sistema de usuários"""
    # CPF e senha do admin padrão
    ADMIN_CPF = "12345678901"  # Substitua pelo CPF do administrador
    ADMIN_PASSWORD = "admin123"  # Senha inicial - deve ser alterada
    
    # Limpar CPF para comparação
    input_cpf_clean = ''.join(filter(str.isdigit, cpf))
    admin_cpf_clean = ''.join(filter(str.isdigit, ADMIN_CPF))
    
    if input_cpf_clean == admin_cpf_clean and password == ADMIN_PASSWORD:
        # Login bem-sucedido com admin padrão
        user_info = {
            'cpf': f"{ADMIN_CPF[:3]}.{ADMIN_CPF[3:6]}.{ADMIN_CPF[6:9]}-{ADMIN_CPF[9:]}",
            'nome': "Administrador",
            'nivel_acesso': 'admin',
            'email': 'admin@govacademy.com',
            'telefone': ''
        }
        
        # Aviso sobre cadastrar usuários
        st.warning("""
        ⚠️ **SISTEMA DE USUÁRIOS NÃO CONFIGURADO**
        
        Você está usando o usuário admin padrão.
        
        **Ações recomendadas:**
        1. Vá para **Configurações > Usuários**
        2. Cadastre os usuários do sistema
        3. Altere a senha do admin
        4. Remova este usuário padrão quando todos estiverem cadastrados
        """)
        
        return True, "Login realizado com sucesso (admin padrão)", user_info
    else:
        return False, "Credenciais inválidas", None

def render_login_page():
    """Tela de login clean com detalhes em roxo - Border ultra fina"""
    
    # CSS CLEAN COM DETALHES ROXOS - BORDER ULTRA FINA
    st.markdown("""
    <style>
    /* Remove o header padrão do Streamlit */
    [data-testid="stHeader"] {
        display: none;
    }
    
    /* FUNDO FORÇADO - MESMA COR DO SISTEMA */
    html, body, #root, .stApp, [data-testid="stAppViewContainer"] {
        background: #F0F4FF !important;
        background-color: #F0F4FF !important;
        min-height: 100vh !important;
        height: 100% !important;
    }
    
    .block-container {
        max-width: 1400px !important;
        width: 100% !important;
        margin: 0 !important;          
        padding: 1rem 0.5rem !important;  
        box-sizing: border-box !important;
    }
    
    
    /* Logo */
    .login-logo {
        display: block;
        margin: 0 auto 25px auto;
        height: 70px;
        width: auto;
        max-width: 100%;
    }
    
    /* Títulos com mais espaço */
    .login-title {
        text-align: center;
        color: #522b7b;
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 8px;
        font-family: 'Inter', -apple-system, sans-serif;
        line-height: 1.2;
        letter-spacing: -0.2px;
    }
    
    .login-subtitle {
        text-align: center;
        color: #64748b;
        font-size: 16px;
        margin-bottom: 40px;
        font-family: 'Inter', -apple-system, sans-serif;
        line-height: 1.4;
    }
    
    /* Labels SEM emojis */
    .input-label {
        display: block;
        color: #522b7b;
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 8px;
        font-family: 'Inter', -apple-system, sans-serif;
    }
    
    /* Inputs - mais largos para acompanhar o retângulo */
    div[data-testid="stTextInput"] > div > div > input {
        border: 0.3px solid #d1d5db !important;
        border-radius: 6px !important;
        padding: 12px 14px !important;
        font-size: 16px !important;
        background: white !important;
        transition: all 0.2s ease;
        height: 46px !important;
        color: #1e293b !important;
        font-weight: 500 !important;
        width: 1000% !important;
    }
    
    div[data-testid="stTextInput"] > div > div > input:focus {
        border-color: #522b7b !important;
        border-width: 0.3px !important;
        box-shadow: 0 0 0 1px rgba(82, 43, 123, 0.08) !important;
    }
    
    /* TENTATIVA 1 - RESET COMPLETO DO BOTÃO DO OLHO */
    button[kind="secondary"] {
        width: 24px !important;
        height: 24px !important;
        min-width: 24px !important;
        min-height: 24px !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }

    /* TENTATIVA 2 - ESTILO MAIS GERAL */
    div[data-testid="stTextInput"] button:last-child {
        width: 20px !important;
        height: 20px !important;
        min-width: 20px !important;
        min-height: 20px !important;
        padding: 2px !important;
        margin: 0 8px 0 0 !important;
    }

    /* TENTATIVA 3 - FOCAR NO SVG DIRETAMENTE */
    .stTextInput button svg {
        width: 16px !important;
        height: 16px !important;
        transform: scale(0.8) !important;
    }

    /* TENTATIVA 4 - USAR TRANSFORM PARA REDUZIR */
    div[data-testid="stTextInput"] button {
        transform: scale(1.3) !important;
        transform-origin: center !important;
        margin-right: 4px !important;
    }

    /* BOTÃO ENTRAR NO SISTEMA - ROXO SÓLIDO */
    div[data-testid="stForm"] button {
        background: #522b7b !important;  /* ROXO SÓLIDO */
        color: white !important;
        border: none !important;
        padding: 12px !important;
        border-radius: 6px !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        width: 100% !important;
        margin-top: 10px !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    div[data-testid="stForm"] button:hover {
        background: #7e3ca8 !important;  /* ROXO MAIS CLARO NO HOVER */
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(82, 43, 123, 0.25);
    }
    
    /* Linha decorativa - mais larga */
    .login-divider {
        height: 0.3px;
        background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.1), transparent);
        margin: 30px 0;
        border: none;
        width: 100%;
    }
    
    /* Rodapé - mais largo */
    .login-footer {
        text-align: center;
        margin-top: 30px;
        color: #64748b;
        font-size: 14px;
        line-height: 1.5;
        width: 100%;
    }
    
    /* Badge de segurança */
    .security-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: #f8f7ff;
        color: #7c3aed;
        padding: 8px 16px;
        border-radius: 18px;
        font-size: 13px;
        font-weight: 600;
        margin-top: 15px;
        border: 0.3px solid #f0edff;
    }
    
    /* Ajuste do formulário para ocupar toda largura */
    div[data-testid="stForm"] {
        width: 100%;
    }
    
    /* Responsivo */
    @media (max-width: 768px) {
        .login-rectangle {
            width: 100% !important;
            padding: 35px 30px;
            margin: 0 auto;
            max-width: 95%;
        }
        
        .login-title {
            font-size: 28px;
        }
        
        .login-subtitle {
            font-size: 15px;
            margin-bottom: 35px;
        }
        
        .login-logo {
            height: 60px;
        }
    }
    
    @media (min-width: 1200px) {
        .login-rectangle {
            width: 600px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Container principal
    with st.container():
        # RETÂNGULO COM BORDA ULTRA FINA E MAIS LARGO
        st.markdown('<div class="login-rectangle">', unsafe_allow_html=True)
        
        # Logo
        logo_local = carregar_logo()
        if logo_local:
            logo_base64 = logo_to_base64(logo_local)
            st.markdown(f'<img src="data:image/png;base64,{logo_base64}" class="login-logo">', unsafe_allow_html=True)
        else:
            st.markdown('''
            <div style="text-align: center; margin-bottom: 25px;">
                <div style="background: linear-gradient(135deg, #522b7b 0%, #7e3ca8 100%); 
                    width: 70px; height: 70px; border-radius: 12px; 
                    display: inline-flex; align-items: center; justify-content: center; 
                    color: white; font-size: 24px;">
                    🔐
                </div>
            </div>''', unsafe_allow_html=True)
        
        st.markdown('<div class="login-title">Gestão de Leads</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">Gov Academy | Sistema Interno</div>', unsafe_allow_html=True)
        
        # Formulário
        with st.form("login_form", clear_on_submit=False):
            # CPF
            st.markdown('<span class="input-label">CPF</span>', unsafe_allow_html=True)
            cpf_input = st.text_input(
                "Digite seu CPF",
                placeholder="000.000.000-00",
                label_visibility="collapsed",
                key="login_cpf"
            )
            
            # SENHA 
            st.markdown('<span class="input-label">Senha</span>', unsafe_allow_html=True)
            
            password_input = st.text_input(
                "Digite sua senha", 
                placeholder="••••••••",
                type="password",
                label_visibility="collapsed",
                key="login_password"
            )
            
            # Botão de login
            submit_button = st.form_submit_button(
                "🔐 ENTRAR NO SISTEMA",
                use_container_width=True,
                type="primary"
            )
        
        # Linha decorativa ultra fina
        st.markdown('<hr class="login-divider">', unsafe_allow_html=True)
        
        # Rodapé
        st.markdown("""
        <div class="login-footer">
            <div style="margin-bottom: 12px; color: #475569; font-weight: 500; font-size: 14px;">
                Acesso restrito a usuários autorizados
            </div>
            <div class="security-badge">
                <span style="color: #7c3aed;">🔒</span> Conexão segura via SSL
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)  
    
    # Processar login (mantido igual)
    if submit_button:
        if not cpf_input or not password_input:
            st.error("❌ Por favor, preencha todos os campos.")
        else:
            allowed, message = check_login_attempts()
            if not allowed:
                st.error(f"⏳ {message}")
            else:
                with st.spinner("Verificando credenciais..."):
                    success, message, user_info = verify_credentials(cpf_input, password_input)
                    
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.user_info = user_info
                        st.session_state.login_attempts = 0
                        st.success(f"✅ {message}")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.session_state.login_attempts += 1
                        st.session_state.last_attempt_time = time.time()
                        st.error(f"❌ {message}")
                        attempts_left = 5 - st.session_state.login_attempts
                        if attempts_left > 0:
                            st.info(f"⚠️ {attempts_left} tentativa(s) restante(s)")

def render_header_menu():
    """Renderiza o menu superior da aplicação com logout"""
    st.markdown("""
    <style>
    /* Estilo para os botões do menu */
    .stButton > button[kind="secondary"] {
        height: 10px;
        margin: 0 2px;
        white-space: nowrap;
        font-size: 14px;
        font-weight: 600;
    }
    
    /* Container do header */
    .header-container {
        background-color: white;
        padding: 10px 0;
        border-bottom: 1px solid #e2e8f0;
        margin-bottom: 25px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="header-container">', unsafe_allow_html=True)
    
    # Layout principal com 3 colunas
    col_logo, col_menu, col_user = st.columns([2, 7, 3])
    
    # Logo
    with col_logo:
        logo_local = carregar_logo()
        if logo_local:
            logo_base64 = logo_to_base64(logo_local)
            st.markdown(f'''
            <div style="display: flex; align-items: center; height: 100%;">
                <img src="data:image/png;base64,{logo_base64}" 
                     style="height: {LOGO_HEIGHT}px; width: auto; margin-left: 5px;">
            </div>
            ''', unsafe_allow_html=True)
    
    # Menu de navegação - Horizontal fixo
    if st.session_state.authenticated:
        with col_menu:
            # Forçar altura do container
            st.markdown('<div style="height: 50px; display: flex; align-items: center;">', unsafe_allow_html=True)
            
            menu_items = [
                ("📊 Dashboard", "Dashboard"),
                ("📝 Cadastrar", "Cadastrar"),
                ("👥 Leads", "Leads"),
                ("🎓 Cursos", "Cursos"),
                ("📈 Relatórios", "Relatórios")
            ]
            
            # Criar uma linha de botões
            menu_cols = st.columns(len(menu_items))
            for i, (label, key) in enumerate(menu_items):
                with menu_cols[i]:
                    if st.button(label, 
                               key=f"nav_{key}", 
                               use_container_width=True, 
                               type="secondary"):
                        st.session_state.menu_atual = key
                        st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Área do usuário e logout - Alinhado à direita
        with col_user:
            st.markdown('<div style="height: 50px; display: flex; align-items: center; justify-content: flex-end; gap: 10px;">', unsafe_allow_html=True)
            
            # Informação do usuário
            user_name = st.session_state.user_info.get('nome', 'Usuário')
            
            # Container para usuário e botão de logout
            user_col1, user_col2 = st.columns([1, 1])
            
            with user_col1:
                if st.button("🚪 Sair", 
                        key="logout_button", 
                        use_container_width=True, 
                        type="secondary"):
                    
                    # Limpar sessão
                    for key in list(st.session_state.keys()):
                        if key not in ['login_attempts', 'last_attempt_time']:
                            del st.session_state[key]
        
                    st.session_state.authenticated = False
                    st.session_state.user_info = {}
                    st.rerun()
            
            with user_col2:
                st.markdown(f'''
                <div style="
                    background: #522b7b;
                    color: #ffffff;
                    padding: 8px 12px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    border: 1px solid #e2e8f0;
                    height: 38px;
                    min-width: 120px;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                ">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="#ffffff">
                        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                    </svg>
                    <span title="{user_name}">{user_name[:15]}{'...' if len(user_name) > 15 else ''}</span>
                </div>
                ''', unsafe_allow_html=True)

# ============================================================================
# 5. FUNÇÕES DE DADOS (GOOGLE SHEETS) 
# ============================================================================
@st.cache_resource
def init_gsheets():
    """Inicializa conexão com Google Sheets usando arquivo de credenciais"""
    try:
        creds = get_credentials()
        if creds is None:
            st.error("Não foi possível obter credenciais")
            return None
            
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

# ============================================================================
# 6. FUNÇÕES AUXILIARES PARA CREDENCIAIS
# ============================================================================
def get_credentials():
    """Retorna credenciais - funciona local e na nuvem"""
    try:
        # Verifica se estamos no Streamlit Cloud (tem secrets)
        try:
            # Tenta acessar secrets - funciona no Streamlit Cloud
            if hasattr(st, 'secrets') and st.secrets:
                # Verifica se tem as chaves necessárias
                required_keys = ['project_id', 'private_key', 'client_email']
                if all(key in st.secrets for key in required_keys):
                    creds_dict = {
                        "type": "service_account",
                        "project_id": st.secrets["project_id"],
                        "private_key_id": st.secrets.get("private_key_id", ""),
                        "private_key": st.secrets["private_key"].replace('\\n', '\n'),
                        "client_email": st.secrets["client_email"],
                        "client_id": st.secrets.get("client_id", ""),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_x509_cert_url": st.secrets.get("client_x509_cert_url", ""),
                        "universe_domain": "googleapis.com"
                    }
                    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except Exception as secrets_error:
            # Não é erro crítico, continua tentando outras opções
            pass
        
        # Para desenvolvimento local - tenta arquivo
        import os
        
        # Caminhos possíveis para o arquivo de credenciais
        caminhos_tentados = [
            r"C:\Users\Natalia Bastos\sistema_leads\creds\service_account.json",
            "./creds/service_account.json",
            "creds/service_account.json",
            os.path.join(os.path.dirname(__file__), "creds", "service_account.json"),
            os.path.join(os.path.dirname(__file__), "service_account.json"),
            "service_account.json"
        ]
        
        for caminho in caminhos_tentados:
            if os.path.exists(caminho):
                try:
                    return Credentials.from_service_account_file(caminho, scopes=SCOPES)
                except Exception as file_error:
                    continue  # Tenta o próximo caminho
        
        # Se chegou aqui, não encontrou credenciais
        st.error("""
        ❌ **Não foi possível carregar as credenciais do Google Sheets**
        
        Para desenvolvimento local, você precisa de UMA destas opções:
        
        **Opção 1:** Ter o arquivo `service_account.json` na pasta `creds/`
        **Opção 2:** Configurar o arquivo `.streamlit/secrets.toml`
        
        Arquivo esperado em: `C:\\Users\\Natalia Bastos\\sistema_leads\\creds\\service_account.json`
        
        Para produção no Streamlit Cloud, configure os secrets no painel da aplicação.
        """)
        
        # Mostra informações de debug
        with st.expander("🔍 Informações de debug"):
            st.write("**Caminhos verificados:**")
            for caminho in caminhos_tentados:
                existe = "✅ EXISTE" if os.path.exists(caminho) else "❌ NÃO EXISTE"
                st.write(f"- {existe}: {caminho}")
            
            st.write(f"\n**Diretório atual:** {os.getcwd()}")
            st.write(f"**Caminho do script:** {os.path.dirname(__file__)}")
        
        return None
            
    except Exception as e:
        st.error(f"Erro ao carregar credenciais: {str(e)}")
        return None
    
# ============================================================================
# 7. FUNÇÕES DE SUPORTE
# ============================================================================
def carregar_logo():
    """Carrega logo da empresa - funciona local e na nuvem"""
    try:
        # Tenta carregar de vários lugares possíveis
        caminhos_possiveis = [
            "./logo-gov-academy.png",          # No repositório Git (funciona na nuvem)
            "logo-gov-academy.png",            # No diretório atual
            r"C:\Users\Natalia Bastos\sistema_leads\logo-gov-academy.png"  # Local
        ]
        
        for caminho in caminhos_possiveis:
            if os.path.exists(caminho):
                return Image.open(caminho)
        
        # Se não encontrar em nenhum lugar
        st.warning("⚠️ Logo não encontrada")
        return None
        
    except Exception as e:
        st.error(f"Erro ao carregar logo: {e}")
        return None
    
def logo_to_base64(image):
    """Converte imagem para base64 - com tratamento de erro"""
    if image is None:
        return None  # Retorna None se a imagem for None
    
    try:
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        st.error(f"Erro ao converter logo para base64: {e}")
        return None

# ============================================================================
# 8. CSS — ESTRUTURAL 
# ============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

/* ===============================
   REMOVE HEADER
   =============================== */
[data-testid="stHeader"] {
    display: none;
}

/* ===============================
   APP BASE
   =============================== */
html, body, .stApp {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
}

/* ===============================
   CONTAINER PRINCIPAL
   =============================== */
.block-container {
    max-width: 1400px !important;
    width: 100% !important;
    margin: 0 auto !important;
    padding: 1rem 2rem !important;
    box-sizing: border-box !important;
}

/* ===============================
   FIX REAL DO st.form
   =============================== */
[data-testid="stForm"],
[data-testid="stForm"] > div,
[data-testid="stForm"] form {
    width: 100% !important;
    max-width: 100% !important;
}

/* ===============================
   FIX DAS COLUMNS
   =============================== */
[data-testid="column"] {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    flex: 1 1 0% !important;
}

/* Remove padding interno das colunas (CORTE REAL) */
[data-testid="column"] > div {
    padding-left: 0 !important;
    padding-right: 0 !important;
}

/* Espaçamento controlado entre colunas */
[data-testid="column"] {
    padding: 0 0.75rem !important;
}

/* ===============================
   CARD
   =============================== */
.white-card {
    width: 100% !important;
    max-width: 100% !important;
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    border: 1px solid #e2e8f0;
    box-sizing: border-box !important;
}

/* ===============================
   CONTAINERS DOS CAMPOS
   =============================== */
.stTextInput,
.stNumberInput,
div[data-baseweb="select"],
.stDateInput {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    overflow: visible !important;
}

/* ===============================
   INPUTS E SELECTS
   =============================== */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
div[data-baseweb="select"] > div,
.stDateInput > div > div > input {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;

    height: 48px !important;
    padding: 0 14px !important;
    box-sizing: border-box !important;

    border: 2px solid #cbd5e1 !important;
    border-radius: 8px !important;
    background-color: #ffffff !important;
    color: #1e293b !important;
    font-size: 16px !important;
    font-weight: 500 !important;
}

/* ===============================
   FIX BASEWEB SELECT
   =============================== */
div[data-baseweb="select"] > div > div {
    display: flex !important;
    align-items: center !important;
    height: 100% !important;
    padding: 0 !important;
}

/* ===============================
   LABELS
   =============================== */
label[data-testid="stWidgetLabel"] p {
    color: #1e293b !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    margin-bottom: 8px !important;
}

/* ===============================
   CAMPOS DE DATA ESPECÍFICOS
   =============================== */
.stDateInput > div > div > input {
    background-color: white !important;
    border: 2px solid #cbd5e1 !important;
    border-radius: 10px !important;
    padding: 12px 16px !important;
    font-size: 16px !important;
    color: #334155 !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
    min-height: 48px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}

/* Foco no campo de data */
.stDateInput > div > div > input:focus {
    border-color: #522b7b !important;
    box-shadow: 0 0 0 3px rgba(82, 43, 123, 0.15) !important;
    outline: none !important;
}

/* Icone do calendário */
.stDateInput > div > div > div > button {
    background-color: transparent !important;
    border: none !important;
    color: #64748b !important;
}

/* Calendário dropdown */
div[data-baseweb="calendar"] {
    background-color: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
}

/* Dias do calendário */
div[data-baseweb="calendar"] button {
    color: #334155 !important;
    font-weight: 500 !important;
}

/* Dia selecionado */
div[data-baseweb="calendar"] button[aria-selected="true"] {
    background-color: #522b7b !important;
    color: white !important;
    font-weight: 600 !important;
}

/* Hoje no calendário */
div[data-baseweb="calendar"] button[data-testid="today"] {
    border: 2px solid #522b7b !important;
    color: #522b7b !important;
}
            
.stButton > button {
    transition: all 0.3s ease !important;
}

.stButton > button {
    transition: all 0.3s ease !important;
}

/* Botão secundário */
button[kind="secondary"] {
    border: 1px solid #e2e8f0 !important;
}

/* Botão secundário - hover (agora em roxo) */
button[kind="secondary"]:hover {
    background-color: rgba(82, 43, 123, 0.05) !important;
    border-color: #8b5cf6 !important;
    color: #8b5cf6 !important;
}

/* Botão secundário - active (também em roxo) */
button[kind="secondary"]:active {
    background-color: rgba(82, 43, 123, 0.1) !important;
    border-color: #522b7b !important;
    color: #522b7b !important;
}
            
/* ===============================
   ESTILOS PARA MULTISELECT
   =============================== */
div[data-baseweb="select"] [role="option"] {
    padding: 10px !important;
}

/* Container do multiselect */
.stMultiSelect > div > div {
    min-height: 48px !important;
}

/* Tags selecionadas no multiselect */
.stMultiSelect [data-baseweb="tag"] {
    margin: 2px !important;
    background-color: #f1f5f9 !important;
    border-color: #cbd5e1 !important;
}
            
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 9. CSS — CORES / TEMA
# ============================================================================

st.markdown(f"""
<style>
.stApp {{
    background-color: {BG_COLOR} !important;
    font-family: 'Inter', sans-serif;
}}

.stTextInput input:focus,
.stNumberInput input:focus,
div[data-baseweb="select"]:focus-within,
.stDateInput > div > div > input:focus {{
    border-color: {PRIMARY_COLOR} !important;
    box-shadow: 0 0 0 3px rgba(82, 43, 123, 0.12) !important;
    outline: none !important;
}}

.gov-purple-btn button {{
    width: 100% !important;
    background: linear-gradient(135deg, {PRIMARY_COLOR} 0%, #7e3ca8 100%) !important;
    color: white !important;
    border-radius: 50px !important;
    padding: 12px !important;
    font-weight: 700 !important;
    border: none !important;
    margin-top: 15px !important;
}}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 10. CSS — CHECKBOX COM REALCE 
# ============================================================================

st.markdown("""
<style>
/* Realce forte para checkbox selecionado */
div[data-testid="stCheckbox"]:has(input:checked) label {
    background-color: #f3e8ff !important;
    border: 2px solid #8b5cf6 !important;
    border-radius: 10px !important;
    padding: 12px 16px !important;
    margin: 6px 0 !important;
    font-weight: 700 !important;
    color: #7c3aed !important;
    box-shadow: 0 2px 8px rgba(139, 92, 246, 0.2) !important;
}

/* Checkbox maior e colorido */
div[data-testid="stCheckbox"] input[type="checkbox"] {
    transform: scale(1.4) !important;
    margin-right: 12px !important;
    accent-color: #7c3aed !important;
}

/* Adiciona ícone de verificação */
div[data-testid="stCheckbox"]:has(input:checked) label::before {
    content: "✅ " !important;
    margin-right: 8px !important;
}

/* Label para campo obrigatório */
.required-field::after {
    content: " *" !important;
    color: #dc2626 !important;
}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 11. FUNÇÕES DE DADOS
# ============================================================================

def get_valores_padrao():
    """Retorna valores padrão para dropdowns"""
    return {
        'origens': ['Google Ads', 'Instagram', 'LinkedIn', 'Indicação', 'Site/Blog', 'Evento/Palestrante', 'Email Marketing', 'Outro'],
        'status': ['Novo', 'Contatado', 'Qualificado', 'Proposta_Enviada', 'Negociação', 'Convertido', 'Perdido'],
        'classificacoes': ['Quente', 'Morno', 'Frio'],
        'estados': ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 
                   'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'],
        'cargos': ['CEO/Diretor', 'Gerente', 'Coordenador', 'Supervisor', 'Analista', 
                  'Assistente', 'Estagiário', 'Autônomo'],
        'interesses': ['Curso Básico', 'Curso Avançado', 'Mentoria', 'Consultoria', 
                      'Certificação', 'Workshop', 'Material Didático', 'Outro'],
        'produtos': ['Curso Básico', 'Curso Avançado', 'Mentoria', 'Consultoria'],
        'canais': ['Email', 'Telefone', 'WhatsApp', 'Presencial'],
        'tipos_cliente': [],  # Agora vazio, será carregado da planilha configuracoes
        'tags': ['Prioridade Alta', 'Recontatar', 'Cliente Potencial', 'Seguir-up', 'Promoção'],
        'equipe': [],  # Será preenchido da planilha
        'cidades': {}
    }

def carregar_cidades_por_estado():
    """Carrega cidades organizadas por estado"""
    cidades_por_estado = {}
    
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        worksheet = planilha.worksheet('cidades_por_estado')
        
        dados = worksheet.get_all_values()
        if not dados or len(dados) <= 1:
            return {}

        df = pd.DataFrame(dados[1:], columns=dados[0])
        
        # Padronização de colunas
        df.columns = [col.strip() for col in df.columns]
        
        # Identificar colunas automaticamente
        col_uf = None
        col_mun = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'uf' in col_lower:
                col_uf = col
                break
        
        for col in df.columns:
            col_lower = col.lower()
            if 'município' in col_lower or 'cidade' in col_lower:
                col_mun = col
                break
        
        # Fallback para colunas padrão
        if not col_uf and len(df.columns) > 0:
            col_uf = df.columns[0]
        if not col_mun and len(df.columns) > 1:
            col_mun = df.columns[1]
        elif not col_mun and len(df.columns) > 0:
            col_mun = df.columns[0]
        
        if not col_uf or not col_mun:
            return {}
        
        # Limpeza dos dados
        df[col_uf] = df[col_uf].astype(str).str.strip().str.upper()
        df[col_mun] = df[col_mun].astype(str).str.strip()
        
        # Remover linhas vazias
        df = df[df[col_uf].notna() & (df[col_uf] != '')]
        df = df[df[col_mun].notna() & (df[col_mun] != '')]
        
        # Agrupar no dicionário
        for estado in df[col_uf].unique():
            estado = str(estado).strip().upper()
            if not estado or len(estado) != 2:
                continue
                
            municipios = df[df[col_uf] == estado][col_mun].dropna().unique().tolist()
            municipios_filtrados = []
            for m in municipios:
                m_str = str(m).strip()
                if m_str and m_str.lower() != 'nan' and m_str != '':
                    municipios_filtrados.append(m_str)
            
            if municipios_filtrados:
                cidades_por_estado[estado] = sorted(municipios_filtrados)
        
        return cidades_por_estado

    except Exception:
        return {}

def carregar_opcoes_dropdown():
    """Carrega opções para dropdowns"""
    opcoes = get_valores_padrao()
    
    try:
        # Carregar configurações
        creds = get_credentials()
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        
        # Configurações
        worksheet = planilha.worksheet('configuracoes')
        dados = worksheet.get_all_values()
        
        if dados and len(dados) > 1:
            df_config = pd.DataFrame(dados[1:], columns=dados[0])

            # Mapeamento de colunas
            mapeamento = {
                'origens': 'Origens', 'status': 'Status', 'classificacoes': 'Classificacoes',
                'estados': 'Estados', 'cargos': 'Cargos_Comuns', 'interesses': 'Interesses',
                'produtos': 'Produto', 'canais': 'Canais_Preferidos', 'tipos_cliente': 'Tipos_Cliente',
                'tags': 'Tags'
            }

            for chave, coluna in mapeamento.items():
                if coluna in df_config.columns:
                    opcoes[chave] = [str(x).strip() for x in df_config[coluna].dropna().tolist() if str(x).strip()]

        # Carregar equipe da aba 'equipe'
        try:
            worksheet_equipe = planilha.worksheet('equipe')
            dados_equipe = worksheet_equipe.get_all_values()
            if dados_equipe and len(dados_equipe) > 1:
                # Assume que a primeira coluna tem os nomes
                df_equipe = pd.DataFrame(dados_equipe[1:], columns=dados_equipe[0])
                # Pega os nomes da primeira coluna disponível
                primeira_coluna = df_equipe.columns[0]
                opcoes['equipe'] = [str(x).strip() for x in df_equipe[primeira_coluna].dropna().tolist() if str(x).strip()]
            else:
                opcoes['equipe'] = []
        except Exception:
            opcoes['equipe'] = []

        # Carregar cidades
        if not st.session_state.opcoes.get('cidades'):
            cidades_carregadas = carregar_cidades_por_estado()
            st.session_state.opcoes['cidades'] = cidades_carregadas
        
        opcoes['cidades'] = st.session_state.opcoes['cidades']
        
        return opcoes

    except Exception:
        # Em caso de erro, usar valores padrão
        cidades_carregadas = carregar_cidades_por_estado()
        st.session_state.opcoes['cidades'] = cidades_carregadas
        opcoes['cidades'] = cidades_carregadas
        opcoes['equipe'] = []
        opcoes['tags'] = []
        return opcoes

def salvar_lead_no_google_sheets(novo_lead):
    """Salva um novo lead no Google Sheets com validação de e-mail duplicado"""
    try:
        # VALIDAÇÃO: Verificar se o e-mail já existe
        email = novo_lead.get('Email', '')
        if email:
            resultado_verificacao = verificar_email_existente(email)
            
            if resultado_verificacao['existe']:
                # Montar mensagem de erro detalhada
                mensagem_erro = f"""
                ⚠️ **E-MAIL JÁ CADASTRADO!**
                
                O e-mail **{email}** já está cadastrado no sistema.
                
                **Lead existente:**
                - **Nome:** {resultado_verificacao.get('nome', 'Não informado')}
                - **ID:** {resultado_verificacao.get('id', 'Não informado')}
                - **Data de Cadastro:** {resultado_verificacao.get('data_cadastro', 'Não informada')}
                
                **Ação necessária:**
                1. Verifique se é o mesmo lead
                2. Se for um novo lead, use um e-mail diferente
                3. Se for o mesmo lead, use a opção de edição na página "Leads"
                """
                st.error(mensagem_erro)
                return False
        
        # Se o e-mail não existe, prosseguir com o cadastro
        creds = get_credentials()
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        worksheet = planilha.worksheet('leads')
        
        # Obter cabeçalhos
        cabecalhos = worksheet.row_values(1)
        
        # Se não houver coluna ID, adicionar
        if 'ID' not in cabecalhos:
            cabecalhos.insert(0, 'ID')
            worksheet.insert_row(cabecalhos, 1)
            # Recarregar cabeçalhos
            cabecalhos = worksheet.row_values(1)
        
        # Garantir que o lead tenha ID
        if 'ID' not in novo_lead:
            # Gerar ID automático
            from datetime import datetime
            lead_id = f"L{datetime.now().strftime('%Y%m%d%H%M%S')}"
            novo_lead['ID'] = lead_id
        
        # Preparar dados na ordem dos cabeçalhos
        dados_para_salvar = []
        for cabecalho in cabecalhos:
            if cabecalho in novo_lead:
                dados_para_salvar.append(novo_lead[cabecalho])
            else:
                dados_para_salvar.append('')
        
        # Adicionar nova linha
        worksheet.append_row(dados_para_salvar)
        return True
        
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False
    
# ============================================================================
# 12. FUNÇÕES PARA EDITAR E EXCLUIR LEADS
# ============================================================================

def deletar_lead_do_google_sheets(lead_id):
    """Deleta um lead do Google Sheets pelo ID"""
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        worksheet = planilha.worksheet('leads')
        
        # Buscar todas as linhas
        dados = worksheet.get_all_values()
        if not dados or len(dados) <= 1:
            return False
        
        # Encontrar a linha com o ID
        cabecalhos = dados[0]
        try:
            coluna_id_index = cabecalhos.index('ID')
        except ValueError:
            # Tentar encontrar por outras colunas de ID
            for i, cabecalho in enumerate(cabecalhos):
                if 'id' in cabecalho.lower():
                    coluna_id_index = i
                    break
            else:
                return False
        
        # Procurar pelo lead_id
        linha_para_excluir = None
        for i, linha in enumerate(dados[1:], start=2):  # start=2 porque a primeira linha é cabeçalho
            if i-1 < len(dados) and coluna_id_index < len(linha):
                if linha[coluna_id_index] == str(lead_id):
                    linha_para_excluir = i
                    break
        
        if linha_para_excluir:
            worksheet.delete_rows(linha_para_excluir)
            
            # LIMPAR O CACHE DOS LEADS
            st.cache_data.clear()  # Limpa todo o cache de dados
            
            return True
        return False
        
    except Exception as e:
        st.error(f"Erro ao deletar lead: {e}")
        return False

def atualizar_lead_no_google_sheets(lead_id, dados_atualizados):
    """Atualiza um lead existente no Google Sheets"""
    try:
        creds = get_credentials()
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        worksheet = planilha.worksheet('leads')
        
        # Buscar todas as linhas
        dados = worksheet.get_all_values()
        if not dados or len(dados) <= 1:
            return False
        
        cabecalhos = dados[0]
        
        # Encontrar a linha com o ID
        try:
            coluna_id_index = cabecalhos.index('ID')
        except ValueError:
            for i, cabecalho in enumerate(cabecalhos):
                if 'id' in cabecalho.lower():
                    coluna_id_index = i
                    break
            else:
                return False
        
        # Procurar pelo lead_id
        linha_para_atualizar = None
        for i, linha in enumerate(dados[1:], start=2):
            if i-1 < len(dados) and coluna_id_index < len(linha):
                if linha[coluna_id_index] == str(lead_id):
                    linha_para_atualizar = i
                    break
        
        if linha_para_atualizar:
            # Preparar dados na ordem dos cabeçalhos
            dados_atualizados_ordenados = []
            for cabecalho in cabecalhos:
                if cabecalho in dados_atualizados:
                    dados_atualizados_ordenados.append(dados_atualizados[cabecalho])
                else:
                    dados_atualizados_ordenados.append('')
            
            # Atualizar a linha
            worksheet.update(f'A{linha_para_atualizar}', [dados_atualizados_ordenados])
            
            # LIMPAR O CACHE DOS LEADS
            st.cache_data.clear()  # Limpa todo o cache de dados
            
            return True
        return False
        
    except Exception as e:
        st.error(f"Erro ao atualizar lead: {e}")
        return False
    

# ============================================================================
# 13. FUNÇÕES PARA CARREGAR DADOS
# ============================================================================

def limpar_numeros(texto):
    """Remove tudo que não é número"""
    if not texto:
        return ''
    return ''.join(filter(str.isdigit, str(texto)))

@st.cache_data(ttl=60)
def load_leads():
    """Carrega dados de leads da planilha Google Sheets"""
    try:
        creds = get_credentials()
        
        if creds is None:
            st.error("❌ Credenciais não disponíveis. Não é possível carregar leads.")
            return pd.DataFrame()  # Retorna DataFrame vazio
        
        client = gspread.authorize(creds)
        planilha = client.open_by_key(SPREADSHEET_ID)
        worksheet = planilha.worksheet('leads')
        
        dados = worksheet.get_all_values()
        
        if not dados or len(dados) <= 1:
            st.info("📭 Nenhum lead cadastrado ainda.")
            return pd.DataFrame()
        
        df = pd.DataFrame(dados[1:], columns=dados[0])
        
        if 'ID' not in df.columns:
            df['ID'] = ''
        
        return df
        
    except gspread.exceptions.APIError as e:
        st.error(f"❌ Erro na API do Google Sheets: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Erro ao carregar leads: {e}")
        return pd.DataFrame()
    
def verificar_email_existente(email):
    """Verifica se o e-mail já existe na planilha de leads"""
    try:
        df_leads = load_leads()
        
        if df_leads.empty:
            return {'existe': False}
        
        if 'Email' in df_leads.columns:
            # Converter para minúsculas para comparação case-insensitive
            emails_existentes = df_leads['Email'].astype(str).str.lower().fillna('').tolist()
            email_lower = str(email).strip().lower()
            
            # Verificar se o e-mail já existe
            if email_lower in emails_existentes:
                # Encontrar o lead existente para mostrar informações
                lead_existente = df_leads[df_leads['Email'].astype(str).str.lower() == email_lower]
                if not lead_existente.empty:
                    return {
                        'existe': True,
                        'nome': lead_existente.iloc[0].get('Nome', ''),
                        'id': lead_existente.iloc[0].get('ID', ''),
                        'data_cadastro': lead_existente.iloc[0].get('Data_Cadastro', ''),
                        'empresa': lead_existente.iloc[0].get('Ente', '')
                    }
            return {'existe': False}
        return {'existe': False}
        
    except Exception as e:
        st.error(f"Erro ao verificar e-mail: {e}")
        return {'existe': False}
    
# ============================================================================
# 14. FUNÇÃO TEMPORÁRIA PARA ANÁLISE CRUZADA
# ============================================================================

def analisar_cruzar_dados(df_leads, df_cursos):
    """
    Função temporária para análise cruzada
    Você vai substituir pela sua função real depois
    """
    try:
        # Verificar se os DataFrames têm dados
        if df_leads.empty:
            return {
                'status': 'erro',
                'mensagem': 'Base de leads vazia'
            }
        
        if df_cursos.empty:
            return {
                'status': 'erro', 
                'mensagem': 'Base de cursos vazia'
            }
        
        # SIMULAÇÃO - substitua pela sua lógica real
        total_leads = len(df_leads)
        
        # Contagens simuladas (apenas para mostrar algo)
        leads_participantes_qtd = min(10, total_leads)
        leads_desistentes_qtd = min(5, total_leads - leads_participantes_qtd)
        leads_nao_abordados_qtd = total_leads - leads_participantes_qtd - leads_desistentes_qtd
        
        return {
            'status': 'sucesso',
            'leads_participantes': {
                'quantidade': leads_participantes_qtd,
                'lista': [],
                'df': pd.DataFrame()
            },
            'leads_desistentes': {
                'quantidade': leads_desistentes_qtd,
                'lista': [],
                'df': pd.DataFrame(),
                'motivos_por_municipio': {}
            },
            'leads_nao_abordados': {
                'quantidade': leads_nao_abordados_qtd,
                'lista': [],
                'df': pd.DataFrame()
            }
        }
        
    except Exception as e:
        return {
            'status': 'erro',
            'mensagem': f'Erro na análise: {str(e)}'
        }
    
# ============================================================================
# 15. FUNÇÕES PARA IMPORTAR DADOS DE CURSOS 
# ============================================================================

@st.cache_data(ttl=300)  # Cache de 5 minutos
def importar_dados_cursos_automatico():
    """
    Importa dados das 4 abas de cursos - PARA PRODUÇÃO
    Funciona localmente e no Streamlit Cloud
    """
    try:
        # O arquivo deve estar na mesma pasta do app.py
        arquivo_local = "planilha.xlsx"
        
        # Carregar todas as abas de uma vez
        todas_abas = pd.read_excel(arquivo_local, sheet_name=None, engine='openpyxl')
        
        # Extrair cada aba (com fallback para DataFrame vazio)
        df_agosto = todas_abas.get('agosto', pd.DataFrame())
        df_novembro = todas_abas.get('novembro', pd.DataFrame())
        df_desistencias = todas_abas.get('desistencias', pd.DataFrame())
        df_desistencias_historico = todas_abas.get('desistencias_historico', pd.DataFrame())
        
        # PADRÃO DOS NOVOS CABEÇALHOS
        # ENTE, MUNICIPIO, CONSULTOR, SDR, MOTIVO_OBJECAO
        
        # Padronizar colunas (caso haja variações)
        for df in [df_agosto, df_novembro, df_desistencias, df_desistencias_historico]:
            if not df.empty:
                # Remover espaços extras e padronizar nomes
                df.columns = [col.strip().upper() if isinstance(col, str) else col for col in df.columns]
                
                # Mapear variações para os nomes padronizados
                mapeamento_colunas = {
                    # Para ente
                    'ENTE': 'ENTE',
                    'ENTIDADE': 'ENTE',
                    'ÓRGÃO': 'ENTE',
                    
                    # Para município
                    'MUNICÍPIO': 'MUNICIPIO',
                    'MUNICIPIO': 'MUNICIPIO',
                    'CIDADE': 'MUNICIPIO',
                    'LOCALIDADE': 'MUNICIPIO',
                    
                    # Para consultor
                    'CONSULTOR': 'CONSULTOR',
                    'VENDEDOR': 'CONSULTOR',
                    'RESPONSÁVEL': 'CONSULTOR',
                    
                    # Para SDR
                    'SDR': 'SDR',
                    'ATENDENTE': 'SDR',
                    'ANALISTA': 'SDR',
                    
                    # Para motivo/objeção
                    'MOTIVO_OBJECAO': 'MOTIVO_OBJECAO',
                    'MOTIVO/OBJEÇÃO': 'MOTIVO_OBJECAO',
                    'MOTIVO': 'MOTIVO_OBJECAO',
                    'OBJEÇÃO': 'MOTIVO_OBJECAO',
                    'JUSTIFICATIVA': 'MOTIVO_OBJECAO'
                }
                
                # Aplicar mapeamento
                novos_nomes = {}
                for col in df.columns:
                    if isinstance(col, str):
                        col_upper = col.upper()
                        for padrao, novo_nome in mapeamento_colunas.items():
                            if padrao in col_upper:
                                novos_nomes[col] = novo_nome
                                break
                        if col not in novos_nomes:
                            # Manter o nome se não encontrar no mapeamento
                            novos_nomes[col] = col_upper
                
                df.rename(columns=novos_nomes, inplace=True)
        
        # Log silencioso (apenas para debug se necessário)
        if st.session_state.get('debug_mode', False):
            print(f"📊 Dados carregados: Agosto({len(df_agosto)}), Nov({len(df_novembro)}), "
                  f"Desist({len(df_desistencias)}), Hist({len(df_desistencias_historico)})")
            
            # Mostrar cabeçalhos para debug
            for nome, df_dados in [('Agosto', df_agosto), ('Novembro', df_novembro), 
                                  ('Desistências', df_desistencias), ('Histórico', df_desistencias_historico)]:
                if not df_dados.empty:
                    print(f"  {nome} colunas:", list(df_dados.columns))
        
        return df_agosto, df_novembro, df_desistencias, df_desistencias_historico
        
    except FileNotFoundError:
        st.warning("Arquivo 'planilha.xlsx' não encontrado na pasta do projeto.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
     
# ============================================================================
# 16. APLICAÇÃO PRINCIPAL
# ============================================================================

def main():

    # VERIFICAÇÃO DE LOGIN - PRIMEIRA COISA A FAZER
    if not st.session_state.authenticated:
        render_login_page()
        return
    
    # Carregar opções
    opcoes = carregar_opcoes_dropdown()
    
    # Renderizar menu
    render_header_menu()
    
    # Conteúdo baseado no menu selecionado
    menu = st.session_state.menu_atual

    # TODO: Adicionar verificação de permissões aqui no futuro
    
    if menu == "Dashboard":
        # Dashboard
        df_leads = load_leads()
        
        if not df_leads.empty:
            # ==================== CÁLCULOS DAS MÉTRICAS ====================
            total = len(df_leads)
            novos = len(df_leads[df_leads['Status'] == 'Novo']) if 'Status' in df_leads.columns else 0
            
            # Calcular conversão real (Convertidos / Total)
            convertidos = len(df_leads[df_leads['Status'] == 'Convertido']) if 'Status' in df_leads.columns else 0
            taxa_conversao = (convertidos / total * 100) if total > 0 else 0
            
            # Leads por mês (últimos 6 meses)
            if 'Data_Cadastro' in df_leads.columns:
                try:
                    df_leads['Data_Cadastro'] = pd.to_datetime(df_leads['Data_Cadastro'])
                    leads_por_mes = df_leads.groupby(df_leads['Data_Cadastro'].dt.to_period('M')).size()
                    leads_ultimo_mes = leads_por_mes.iloc[-1] if len(leads_por_mes) > 0 else 0
                    crescimento = "+10%"  # Simulado por enquanto
                except:
                    leads_ultimo_mes = 0
                    crescimento = "N/A"
            else:
                leads_ultimo_mes = 0
                crescimento = "N/A"
            
            # ==================== LAYOUT DO DASHBOARD ====================
            st.markdown("""
            <style>
            .dashboard-header {
                color: #1e293b;
                font-size: 28px;
                font-weight: 800;
                margin-bottom: 10px;
            }
            .dashboard-subtitle {
                color: #64748b;
                font-size: 14px;
                margin-bottom: 30px;
            }
            .metric-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                border: 1px solid #e2e8f0;
                transition: transform 0.2s ease;
                height: 100%;
            }
            .metric-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.05);
            }
            .metric-value {
                font-size: 2.2rem;
                font-weight: 800;
                color: #522b7b;
                margin: 10px 0;
            }
            .metric-label {
                color: #64748b;
                font-size: 0.9rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .metric-delta {
                font-size: 0.85rem;
                font-weight: 600;
                margin-top: 5px;
            }
            .metric-delta.positive {
                color: #10b981;
            }
            .metric-delta.negative {
                color: #ef4444;
            }
            .section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin: 30px 0 20px 0;
                padding-bottom: 0;
                border-bottom: none;
            }
            .section-title {
                font-size: 1.4rem;
                font-weight: 700;
                color: #1e293b;
            }
            .chart-container {
                background: white;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                border: none !important;
                box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            }
            .status-badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 600;
                margin: 2px 4px;
            }
                        
            /* Remover bordas dos gráficos Plotly */
            .js-plotly-plot .plotly .modebar {
                display: none;
            }
            .js-plotly-plot .plotly .main-svg {
                border: none !important;
            }
            .js-plotly-plot .plotly .gridlayer path {
                stroke: none !important;
            }
            .js-plotly-plot .plotly .xaxis path,
            .js-plotly-plot .plotly .yaxis path {
                stroke: none !important;
            }
            .js-plotly-plot .plotly .xaxis line,
            .js-plotly-plot .plotly .yaxis line {
                stroke: none !important;
            }
            </style>
            """, unsafe_allow_html=True)

            # Cabeçalho
            st.markdown('<div class="dashboard-header">📊 Dashboard de Performance</div>', unsafe_allow_html=True)
            
            # ==================== METRICAS PRINCIPAIS ====================
            st.markdown('<h3 style="color: #1e293b; font-size: 1.4rem; font-weight: 700; margin: 0 0 20px 0;">Métricas Principais</h3>', unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Total de Leads</div>
                    <div class="metric-value">{total}</div>
                    <div class="metric-delta {'positive' if novos > 0 else ''}">
                        ↑ {novos} novos este mês
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Taxa de Conversão</div>
                    <div class="metric-value">{taxa_conversao:.1f}%</div>
                    <div class="metric-delta">
                        {convertidos} leads convertidos
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                valor_total = 0  # Removido o cálculo de valor estimado
                valor_formatado = "R$ 0"
                
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Valor Estimado</div>
                    <div class="metric-value">{valor_formatado}</div>
                    <div class="metric-delta">
                        Potencial de receita
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Leads Último Mês</div>
                    <div class="metric-value">{leads_ultimo_mes}</div>
                    <div class="metric-delta {'positive' if crescimento.startswith('+') else 'negative'}">
                        {crescimento} vs mês anterior
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # ==================== GRÁFICOS ====================
            
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown('<h3 style="color: #1e293b; font-size: 1.4rem; font-weight: 700; margin: 30px 0 20px 0;">Análise Visual</h3>', unsafe_allow_html=True)
            
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown('<p style="color: #1e293b; font-size: 1.1rem; font-weight: 700; margin-bottom: 10px;">📈 Distribuição por Status</p>', unsafe_allow_html=True)
                
                if 'Status' in df_leads.columns:
                    status_counts = df_leads['Status'].value_counts()
                    fig_status = px.pie(
                        names=status_counts.index, 
                        values=status_counts.values,
                        color_discrete_sequence=['#522b7b', '#8b5cf6', '#6366f1', '#10b981', '#f59e0b', '#ef4444']
                    )
                    fig_status.update_layout(
                        margin=dict(t=0, b=0, l=0, r=0),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2)
                    )
                    st.plotly_chart(fig_status, use_container_width=True, config={'displayModeBar': False})
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_chart2:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown('<p style="color: #1e293b; font-size: 1.1rem; font-weight: 700; margin-bottom: 10px;">🎯 Origem dos Leads</p>', unsafe_allow_html=True)
                
                if 'Origem_Lead' in df_leads.columns:
                    origem_counts = df_leads['Origem_Lead'].value_counts().head(8)
                    fig_origem = px.bar(
                        x=origem_counts.values,
                        y=origem_counts.index,
                        orientation='h',
                        color_discrete_sequence=['#8b5cf6']
                    )
                    fig_origem.update_layout(
                        margin=dict(t=0, b=0, l=10, r=10),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(showgrid=False, zeroline=False, showline=False),
                        yaxis=dict(showgrid=False, zeroline=False, showline=False),
                        height=300
                    )
                    st.plotly_chart(fig_origem, use_container_width=True, config={'displayModeBar': False})
                st.markdown('</div>', unsafe_allow_html=True)
            
            # ==================== MÉTRICAS SECUNDÁRIAS ====================
            st.markdown('<h3 style="color: #1e293b; font-size: 1.4rem; font-weight: 700; margin: 30px 0 20px 0;">📊 Insights Adicionais</h3>', unsafe_allow_html=True)
            
            col_insight1, col_insight2, col_insight3 = st.columns(3)
            
            with col_insight1:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown('<h3 style="color: #1e293b; font-size: 1rem; margin-bottom: 15px;">🏙️ Top Cidades</h3>', unsafe_allow_html=True)
                
                if 'Cidade' in df_leads.columns:
                    top_cidades = df_leads['Cidade'].value_counts().head(5)
                    for cidade, count in top_cidades.items():
                        porcentagem = (count / total * 100) if total > 0 else 0
                        st.markdown(f"""
                        <div style="margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                <span style="font-weight: 500; color: #475569;">{cidade}</span>
                                <span style="font-weight: 600; color: #522b7b;">{count}</span>
                            </div>
                            <div style="background-color: #f1f5f9; height: 8px; border-radius: 4px;">
                                <div style="background-color: #8b5cf6; width: {porcentagem}%; height: 100%; border-radius: 4px;"></div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Sem dados de cidades")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_insight2:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown('<h3 style="color: #1e293b; font-size: 1rem; margin-bottom: 15px;">🏢 Top Entes</h3>', unsafe_allow_html=True)
                
                if 'Ente' in df_leads.columns:
                    # Separar entes múltiplos e contar
                    all_entes = []
                    for ente_str in df_leads['Ente'].dropna():
                        # Se o ente contém múltiplos valores separados por vírgula
                        if ',' in str(ente_str):
                            entes = [e.strip() for e in str(ente_str).split(',')]
                            all_entes.extend(entes)
                        else:
                            all_entes.append(str(ente_str).strip())
                    
                    # Contar frequência
                    if all_entes:
                        from collections import Counter
                        ente_counter = Counter(all_entes)
                        top_entes = ente_counter.most_common(5)
                        
                        for ente, count in top_entes:
                            porcentagem = (count / total * 100) if total > 0 else 0
                            st.markdown(f"""
                            <div style="margin-bottom: 10px;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                    <span style="font-weight: 500; color: #475569; max-width: 70%; overflow: hidden; text-overflow: ellipsis;">{ente}</span>
                                    <span style="font-weight: 600; color: #522b7b;">{count}</span>
                                </div>
                                <div style="background-color: #f1f5f9; height: 8px; border-radius: 4px;">
                                    <div style="background-color: #10b981; width: {porcentagem}%; height: 100%; border-radius: 4px;"></div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.info("Sem dados de entes")
                else:
                    st.info("Sem dados de entes")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_insight3:
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.markdown('<h3 style="color: #1e293b; font-size: 1rem; margin-bottom: 15px;">🎯 Top Produtos de Interesse</h3>', unsafe_allow_html=True)
                
                if 'Produto_Interesse' in df_leads.columns:
                    produto_counts = df_leads['Produto_Interesse'].value_counts().head(5)
                    colors = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6']
                    
                    for i, (produto, count) in enumerate(produto_counts.items()):
                        color = colors[i] if i < len(colors) else '#94a3b8'
                        porcentagem = (count / total * 100) if total > 0 else 0
                        
                        st.markdown(f"""
                        <div style="margin-bottom: 15px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px;">
                                <span style="display: flex; align-items: center;">
                                    <div style="width: 12px; height: 12px; border-radius: 50%; background-color: {color}; margin-right: 10px;"></div>
                                    <span style="font-weight: 600; color: #475569;">{produto}</span>
                                </span>
                                <span style="font-weight: 700; color: #1e293b;">{porcentagem:.0f}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #64748b;">
                                <span>{count} leads</span>
                                <span>{porcentagem:.1f}% do total</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Sem dados de produtos")
                
                st.markdown('</div>', unsafe_allow_html=True)
        
        else:
            # Caso não haja dados
            st.markdown('<div class="white-card" style="padding: 60px 20px; text-align: center;">', unsafe_allow_html=True)
            st.markdown('<div style="font-size: 48px; margin-bottom: 20px; color: #cbd5e1;">📊</div>', unsafe_allow_html=True)
            st.markdown('<h3 style="color: #475569; font-size: 20px; margin-bottom: 10px;">Dashboard Vazio</h3>', unsafe_allow_html=True)
            st.markdown('<p style="color: #64748b; font-size: 14px; max-width: 500px; margin: 0 auto 30px auto;">Comece a cadastrar leads para visualizar métricas e insights de performance.</p>', unsafe_allow_html=True)
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                if st.button("➕ Cadastrar Primeiro Lead", type="primary", use_container_width=True):
                    st.session_state.menu_atual = "Cadastrar"
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)

    elif menu == "Leads":
        # Lista de Leads
        df_leads = load_leads()
        
        # Inicializar session states para edição
        if 'editing_lead' not in st.session_state:
            st.session_state.editing_lead = None
        if 'delete_confirm' not in st.session_state:
            st.session_state.delete_confirm = None
        
        if not df_leads.empty:
            # Métricas
            total_leads = len(df_leads)
            m1, m2, m3, m4 = st.columns(4)
            
            with m1: render_metric_card("TOTAL DE LEADS", f"{total_leads}")
            with m2: render_metric_card("CARGO MAIS COMUM", 
                df_leads['Cargo_Funcao'].value_counts().index[0] if 'Cargo_Funcao' in df_leads.columns else "N/A")
            with m3: render_metric_card("ENTE PRINCIPAL",
                df_leads['Ente'].value_counts().index[0] if 'Ente' in df_leads.columns else "N/A")
            with m4: render_metric_card("CIDADE LÍDER",
                df_leads['Cidade'].value_counts().index[0] if 'Cidade' in df_leads.columns else "N/A")
            
            # Busca
            st.markdown('<div style="margin-top: 40px;"></div>', unsafe_allow_html=True)
            st.markdown("""
            <div style="margin-bottom: 10px; font-size: 18px; font-weight: 600; color: #1e293b;">
                🔍 Buscar em todos os campos
            </div>
            """, unsafe_allow_html=True)
            
            search_col, btn1_col, btn2_col = st.columns([6, 2, 2])
            
            with search_col:
                search_term = st.text_input(
                    "",
                    value=st.session_state.search_term,
                    placeholder="Digite para buscar...",
                    key="lead_search_input",
                    label_visibility="collapsed"
                )
                
                if search_term != st.session_state.search_term:
                    st.session_state.search_term = search_term
            
            with btn1_col:
                if st.button("🔍 Buscar", type="primary", use_container_width=True):
                    pass
            
            with btn2_col:
                if st.button("🗑️ Limpar", use_container_width=True):
                    st.session_state.search_term = ""
                    st.rerun()
            
            # Aplicar filtro
            st.markdown('<div style="margin-top: 25px;"></div>', unsafe_allow_html=True)
            
            if st.session_state.search_term:
                search_term_lower = st.session_state.search_term.strip().lower()
                mask = pd.Series([False] * len(df_leads))
                
                for col in df_leads.columns:
                    if df_leads[col].dtype == 'object':
                        mask = mask | df_leads[col].astype(str).str.lower().str.contains(search_term_lower, na=False)
                
                filtered_df = df_leads[mask]
                results_count = len(filtered_df)
            else:
                filtered_df = df_leads
                results_count = len(filtered_df)
            
            if results_count > 0:
                st.success(f"🔍 **{results_count} leads encontrados**")
                
                # Se estiver editando um lead, mostrar APENAS o formulário de edição
                if st.session_state.editing_lead:
                    st.markdown('<div class="white-card">', unsafe_allow_html=True)
                    st.subheader("✏️ Editando Lead")
                    
                    lead_para_editar = df_leads[df_leads['ID'] == st.session_state.editing_lead]
                    if not lead_para_editar.empty:
                        lead_para_editar = lead_para_editar.iloc[0]
                        
                        with st.form("editar_lead_completo"):
                            # Seção 1: Dados Pessoais
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 30px; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">👤</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Informações Pessoais</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Nome Completo *</div>', unsafe_allow_html=True)
                                nome_edit = st.text_input("", 
                                    value=lead_para_editar.get('Nome', ''),
                                    placeholder="Digite o nome completo",
                                    label_visibility="collapsed", 
                                    key="nome_edit_completo")
                            
                            with col2:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">E-mail *</div>', unsafe_allow_html=True)
                                email_edit = st.text_input("", 
                                    value=lead_para_editar.get('Email', ''),
                                    placeholder="exemplo@empresa.com",
                                    label_visibility="collapsed", 
                                    key="email_edit_completo")
                            
                            col3, col4 = st.columns(2)
                            
                            with col3:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">CPF</div>', unsafe_allow_html=True)
                                cpf_edit = st.text_input("", 
                                    value=lead_para_editar.get('CPF', ''),
                                    placeholder="000.000.000-00",
                                    label_visibility="collapsed", 
                                    key="cpf_edit_completo")
                            
                            with col4:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Telefone/WhatsApp</div>', unsafe_allow_html=True)
                                telefone_edit = st.text_input("", 
                                    value=lead_para_editar.get('Telefone', ''),
                                    placeholder="(00) 00000-0000",
                                    label_visibility="collapsed", 
                                    key="telefone_edit_completo")
                            
                            # Seção 2: Dados Profissionais
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">💼</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Dados Profissionais</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col5, col6 = st.columns(2)
                            
                            with col5:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Cargo/Função</div>', unsafe_allow_html=True)
                                cargo_edit = st.selectbox("", 
                                    options=[""] + opcoes['cargos'],
                                    index=opcoes['cargos'].index(lead_para_editar.get('Cargo_Funcao', '')) + 1 if lead_para_editar.get('Cargo_Funcao', '') in opcoes['cargos'] else 0,
                                    label_visibility="collapsed", 
                                    key="cargo_edit_completo")
                            
                            with col6:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Ente(s)</div>', unsafe_allow_html=True)
                                # Converter string para lista para o multiselect
                                ente_str = lead_para_editar.get('Ente', '')
                                if ente_str:
                                    # Separar por vírgula e limpar espaços
                                    entes_existentes = [e.strip() for e in str(ente_str).split(',') if e.strip()]
                                else:
                                    entes_existentes = []
                                
                                ente_edit = st.multiselect("", 
                                    options=opcoes['tipos_cliente'],
                                    default=entes_existentes,
                                    label_visibility="collapsed", 
                                    key="ente_edit_completo")
                            
                            # Seção 3: Localização
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">📍</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Localização</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col9, col10 = st.columns(2)
                            
                            with col9:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Estado (UF)</div>', unsafe_allow_html=True)
                                estado_edit = st.selectbox("", 
                                    options=[""] + opcoes['estados'],
                                    index=opcoes['estados'].index(lead_para_editar.get('Estado', '')) + 1 if lead_para_editar.get('Estado', '') in opcoes['estados'] else 0,
                                    label_visibility="collapsed", 
                                    key="estado_edit_completo")
                            
                            with col10:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Cidade</div>', unsafe_allow_html=True)
                                cidade_edit = st.text_input("",
                                    value=lead_para_editar.get('Cidade', ''),
                                    placeholder="Digite o nome da cidade",
                                    key="cidade_edit_completo",
                                    label_visibility="collapsed")
                            
                            # Seção 4: Origem e Interesse
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">🎯</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Origem e Interesse</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col11, col12 = st.columns(2)
                            
                            with col11:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Origem do Lead</div>', unsafe_allow_html=True)
                                origem_lead_edit = st.selectbox("", 
                                    options=[""] + opcoes['origens'],
                                    index=opcoes['origens'].index(lead_para_editar.get('Origem_Lead', '')) + 1 if lead_para_editar.get('Origem_Lead', '') in opcoes['origens'] else 0,
                                    label_visibility="collapsed", 
                                    key="origem_edit_completo")
                            
                            with col12:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Produto de Interesse</div>', unsafe_allow_html=True)
                                produto_interesse_edit = st.selectbox("", 
                                    options=[""] + opcoes['produtos'],
                                    index=opcoes['produtos'].index(lead_para_editar.get('Produto_Interesse', '')) + 1 if lead_para_editar.get('Produto_Interesse', '') in opcoes['produtos'] else 0,
                                    label_visibility="collapsed", 
                                    key="produto_edit_completo")
                            
                            col13, col14 = st.columns(2)
                            
                            with col13:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Canal Preferido</div>', unsafe_allow_html=True)
                                canal_preferido_edit = st.selectbox("", 
                                    options=[""] + opcoes['canais'],
                                    index=opcoes['canais'].index(lead_para_editar.get('Canal_Preferido', '')) + 1 if lead_para_editar.get('Canal_Preferido', '') in opcoes['canais'] else 0,
                                    label_visibility="collapsed", 
                                    key="canal_edit_completo")
                            
                            # Seção 5: Status e Classificação
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #ef4444 0%, #f87171 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">📊</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Status e Classificação</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col15, col16 = st.columns(2)
                            
                            with col15:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Status</div>', unsafe_allow_html=True)
                                status_edit = st.selectbox("", 
                                    options=[""] + opcoes['status'],
                                    index=opcoes['status'].index(lead_para_editar.get('Status', '')) + 1 if lead_para_editar.get('Status', '') in opcoes['status'] else 0,
                                    label_visibility="collapsed", 
                                    key="status_edit_completo")
                            
                            with col16:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Classificação</div>', unsafe_allow_html=True)
                                classificacao_edit = st.selectbox("", 
                                    options=[""] + opcoes['classificacoes'],
                                    index=opcoes['classificacoes'].index(lead_para_editar.get('Classificacao', '')) + 1 if lead_para_editar.get('Classificacao', '') in opcoes['classificacoes'] else 0,
                                    label_visibility="collapsed", 
                                    key="classificacao_edit_completo")

                            # Seção 6: Atribuição e Follow-up
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">👥</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Atribuição e Follow-up</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col17, col18 = st.columns(2)
                            
                            with col17:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Atribuído a</div>', unsafe_allow_html=True)
                                atribuido_a_edit = st.selectbox("", 
                                    options=[""] + opcoes['equipe'],
                                    index=opcoes['equipe'].index(lead_para_editar.get('Atribuido_A', '')) + 1 if lead_para_editar.get('Atribuido_A', '') in opcoes['equipe'] else 0,
                                    label_visibility="collapsed", 
                                    key="atribuido_edit_completo")
                            
                            with col18:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Tag</div>', unsafe_allow_html=True)
                                tag_edit = st.selectbox("", 
                                    options=[""] + opcoes['tags'],
                                    index=opcoes['tags'].index(lead_para_editar.get('Tag', '')) + 1 if lead_para_editar.get('Tag', '') in opcoes['tags'] else 0,
                                    label_visibility="collapsed", 
                                    key="tag_edit_completo")
                            
                            col19, col20 = st.columns(2)
                            
                            with col19:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Data Próximo Contato</div>', unsafe_allow_html=True)
                                # Converter string para data se existir
                                data_proximo_str = lead_para_editar.get('Data_Proximo_Contato', '')
                                if data_proximo_str and data_proximo_str.strip():
                                    try:
                                        data_proximo = datetime.strptime(data_proximo_str, '%Y-%m-%d').date()
                                    except:
                                        data_proximo = None
                                else:
                                    data_proximo = None
                                
                                data_proximo_contato_edit = st.date_input("", 
                                    value=data_proximo,
                                    key="data_proximo_edit_completo",
                                    label_visibility="collapsed")
                            
                            with col20:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Data Convertido</div>', unsafe_allow_html=True)
                                # Converter string para data se existir
                                data_convertido_str = lead_para_editar.get('Data_Convertido', '')
                                if data_convertido_str and data_convertido_str.strip():
                                    try:
                                        data_convertido = datetime.strptime(data_convertido_str, '%Y-%m-%d').date()
                                    except:
                                        data_convertido = None
                                else:
                                    data_convertido = None
                                
                                data_convertido_edit = st.date_input("", 
                                    value=data_convertido,
                                    key="data_convertido_edit_completo",
                                    label_visibility="collapsed")
                            
                            # Seção 7: Preferências
                            st.markdown("""
                            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                                <div style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">📢</div>
                                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Preferências</h3>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col21, col22 = st.columns(2)
                            
                            with col21:
                                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Receber Novidades</div>', unsafe_allow_html=True)
                                receber_novidades_edit = st.selectbox("", 
                                    options=["", "Sim", "Não"],
                                    index=["", "Sim", "Não"].index(lead_para_editar.get('Receber_Novidades', '')) if lead_para_editar.get('Receber_Novidades', '') in ["", "Sim", "Não"] else 0,
                                    label_visibility="collapsed", 
                                    key="novidades_edit_completo")
                            
                            # Observações
                            st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin: 40px 0 8px 0;">Observações</div>', unsafe_allow_html=True)
                            observacoes_edit = st.text_area("", 
                                value=lead_para_editar.get('Observacoes', ''),
                                placeholder="Observações adicionais...",
                                label_visibility="collapsed", 
                                height=100, 
                                key="obs_edit_completo")
                            
                            # Botões de ação DENTRO do form
                            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                            with col_btn2:
                                col_salvar, col_cancelar = st.columns(2)
                                with col_salvar:
                                    salvar_edicao = st.form_submit_button("💾 Salvar Alterações", use_container_width=True)
                                with col_cancelar:
                                    cancelar_btn = st.form_submit_button("❌ Cancelar", use_container_width=True)
                            
                            # PROCESSAMENTO DO FORMULÁRIO DENTRO DO BLOCO with st.form()
                            if salvar_edicao:
                                # VALIDAÇÃO: Verificar se o e-mail foi alterado para um que já existe (exceto se for o mesmo lead)
                                email_atual = lead_para_editar.get('Email', '')
                                novo_email = email_edit

                                if novo_email and novo_email.lower() != email_atual.lower():
                                    resultado_verificacao = verificar_email_existente(novo_email)
                
                                    if resultado_verificacao['existe']:
                                        # Verificar se não é o mesmo lead (por ID)
                                        if resultado_verificacao.get('id') != st.session_state.editing_lead:
                                            st.error(f"""
                                            ⚠️ **E-MAIL JÁ CADASTRADO!**
                            
                                            O e-mail **{novo_email}** já está cadastrado para outro lead.
                            
                                            **Lead existente:**
                                            - **Nome:** {resultado_verificacao.get('nome', 'Não informado')}
                                            - **ID:** {resultado_verificacao.get('id', 'Não informado')}
                                            - **Ente:** {resultado_verificacao.get('empresa', 'Não informado')}
                            
                                            Por favor, use um e-mail diferente ou edite o lead existente.
                                            """)
                                            st.stop()

                                from datetime import datetime
                                # Converter datas para string
                                data_proximo_str_edit = ""
                                data_convertido_str_edit = ""
                                            
                                if data_proximo_contato_edit:
                                    data_proximo_str_edit = data_proximo_contato_edit.strftime("%Y-%m-%d")
                                if data_convertido_edit:
                                    data_convertido_str_edit = data_convertido_edit.strftime("%Y-%m-%d")
                                
                                # Converter lista de entes para string separada por vírgula
                                ente_str_edit = ", ".join(ente_edit) if ente_edit else ""
                                            
                                dados_atualizados = {
                                    'ID': st.session_state.editing_lead,
                                    'Nome': nome_edit,
                                    'Email': email_edit,
                                    'CPF': limpar_numeros(cpf_edit) if cpf_edit else '',
                                    'Telefone': limpar_numeros(telefone_edit) if telefone_edit else '',
                                    'Cargo_Funcao': cargo_edit if cargo_edit else '',
                                    'Ente': ente_str_edit,
                                    'Estado': estado_edit if estado_edit else '',
                                    'Cidade': cidade_edit if cidade_edit else '',
                                    'Origem_Lead': origem_lead_edit if origem_lead_edit else '',
                                    'Produto_Interesse': produto_interesse_edit if produto_interesse_edit else '',
                                    'Canal_Preferido': canal_preferido_edit if canal_preferido_edit else '',
                                    'Status': status_edit if status_edit else 'Novo',
                                    'Classificacao': classificacao_edit if classificacao_edit else '',
                                    'Atribuido_A': atribuido_a_edit if atribuido_a_edit else '',
                                    'Tag': tag_edit if tag_edit else '',
                                    'Data_Proximo_Contato': data_proximo_str_edit,
                                    'Data_Convertido': data_convertido_str_edit,
                                    'Receber_Novidades': receber_novidades_edit if receber_novidades_edit else '',
                                    'Observacoes': observacoes_edit if observacoes_edit else '',
                                    'Ultimo_Contato': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'Ultima_Acao': 'Edição completa via sistema'
                                }
                                            
                                sucesso = atualizar_lead_no_google_sheets(st.session_state.editing_lead, dados_atualizados)
                                if sucesso:
                                    st.success("✅ Lead atualizado com sucesso!")
                                    st.session_state.editing_lead = None
                                    st.rerun()

                            if cancelar_btn:
                                st.session_state.editing_lead = None                        
                                st.rerun()

                    st.markdown('</div>', unsafe_allow_html=True)
                    
                # Se estiver confirmando exclusão, mostrar APENAS a confirmação
                elif st.session_state.delete_confirm:
                    st.markdown('<div class="white-card">', unsafe_allow_html=True)
                    st.warning(f"⚠️ **Tem certeza que deseja excluir o lead com ID {st.session_state.delete_confirm}?**")
                            
                    lead_para_excluir = df_leads[df_leads['ID'] == st.session_state.delete_confirm]
                    if not lead_para_excluir.empty:
                        lead_para_excluir = lead_para_excluir.iloc[0]
                        st.write(f"**Nome:** {lead_para_excluir.get('Nome', 'N/A')}")
                        st.write(f"**E-mail:** {lead_para_excluir.get('Email', 'N/A')}")
                        st.write(f"**Ente:** {lead_para_excluir.get('Ente', 'N/A')}")
                            
                    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                    with col_btn2:
                        col_excluir, col_cancelar = st.columns(2)
                        with col_excluir:
                            if st.button("🗑️ Sim, excluir", type="primary", use_container_width=True):
                                sucesso = deletar_lead_do_google_sheets(st.session_state.delete_confirm)
                                if sucesso:
                                    st.success("✅ Lead excluído com sucesso!")
                                    st.session_state.delete_confirm = None
                                    st.rerun()
                        with col_cancelar:
                            if st.button("↩️ Cancelar", use_container_width=True):
                                st.session_state.delete_confirm = None
                                st.rerun()
                        
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                # Se NÃO estiver editando nem excluindo, mostrar a tabela normal
                else:
                    # Mostrar tabela com os leads
                    st.dataframe(filtered_df, use_container_width=True, hide_index=True, height=400)
                    
                    # Controles de ação abaixo da tabela
                    st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)
                    
                    col_sel, col_edit, col_del = st.columns(3)
                    
                    with col_sel:
                        st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Selecionar Lead</div>', unsafe_allow_html=True)
                        
                        # Criar opções no formato "Nome - Email (ID)" para fácil identificação
                        opcoes_leads = [""]
                        for _, lead in filtered_df.iterrows():
                            nome = lead.get('Nome', 'Sem nome')
                            email = lead.get('Email', 'Sem email')
                            lead_id = lead.get('ID', 'Sem ID')
                            # Formato: "Nome Completo - email@exemplo.com (ID: L123)"
                            display_text = f"{nome} - {email} (ID: {lead_id})"
                            opcoes_leads.append(display_text)
                            
                        lead_selecionado_display = st.selectbox(
                            "", 
                            options=opcoes_leads, 
                            index=0, 
                            label_visibility="collapsed", 
                            key="select_lead"
                        )
                        
                        # Extrair o ID do texto selecionado
                        lead_id_selecionado = None
                        if lead_selecionado_display and lead_selecionado_display != "":
                            # Buscar o ID entre parênteses
                            import re
                            match = re.search(r'\(ID:\s*([^)]+)\)', lead_selecionado_display)
                            if match:
                                lead_id_selecionado = match.group(1).strip()
                    
                    with col_edit:
                        st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Editar</div>', unsafe_allow_html=True)
                        if st.button("✏️ Editar Lead", use_container_width=True, disabled=not lead_id_selecionado):
                            if lead_id_selecionado:
                                st.session_state.editing_lead = lead_id_selecionado
                                st.rerun()
                    
                    with col_del:
                        st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Excluir</div>', unsafe_allow_html=True)
                        if st.button("🗑️ Excluir Lead", use_container_width=True, disabled=not lead_id_selecionado):
                            if lead_id_selecionado:
                                st.session_state.delete_confirm = lead_id_selecionado
                                st.rerun()

                                           
    elif menu == "Cadastrar":

        st.markdown('<div class="white-card full-width-form">', unsafe_allow_html=True)

        # Formulário de Cadastro
        with st.form("novo_lead"):
            # Seção 1: Dados Pessoais
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 30px; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">👤</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Informações Pessoais</h3>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Nome Completo *</div>', unsafe_allow_html=True)
                nome = st.text_input("", placeholder="Digite o nome completo", label_visibility="collapsed", key="nome_input")
            
            with col2:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">E-mail *</div>', unsafe_allow_html=True)
                email = st.text_input("", placeholder="exemplo@empresa.com", label_visibility="collapsed", key="email_input")
            
            col3, col4 = st.columns(2)
            
            with col3:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">CPF</div>', unsafe_allow_html=True)
                cpf = st.text_input("", placeholder="000.000.000-00", label_visibility="collapsed", key="cpf_input")
            
            with col4:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Telefone/WhatsApp</div>', unsafe_allow_html=True)
                telefone = st.text_input("", placeholder="(00) 00000-0000", label_visibility="collapsed", key="telefone_input")
            
            # Seção 2: Dados Profissionais
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">💼</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Dados Profissionais</h3>
            </div>
            """, unsafe_allow_html=True)

            col5, col6 = st.columns(2)

            with col5:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Cargo/Função</div>', unsafe_allow_html=True)
                cargo = st.selectbox("", options=[""] + opcoes['cargos'], index=0, label_visibility="collapsed", key="cargo_input")

            with col6:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Ente(s) <span style="color: #dc2626;">*</span></div>', unsafe_allow_html=True)
    
                # CSS para estilizar o multiselect
                st.markdown("""
                <style>
                /* Container do multiselect */
                .stMultiSelect [data-baseweb="tag"] {
                    display: inline-flex !important;
                    align-items: center !important;
                    height: 28px !important;
                    margin: 2px 4px 2px 0 !important;
                    background-color: white !important;
                }
    
                /* Quando o multiselect está em foco */
                .stMultiSelect > div > div:focus-within {
                    border-color: #8b5cf6 !important;
                    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1) !important;
                }
    
                /* Tags dos itens selecionados */
                .stMultiSelect [data-baseweb="tag"] {
                    background-color: rgba(139, 92, 246, 0.1) !important;
                    color: #7c3aed !important;
                    border-color: #8b5cf6 !important;
                    border-radius: 6px !important;
                    font-weight: 500 !important;
                    margin: 2px !important;
                }
    
                /* Dropdown menu */
                div[data-baseweb="select"] [role="listbox"] {
                    border-radius: 8px !important;
                    border: 1px solid #e2e8f0 !important;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
                }
    
                /* Itens no dropdown */
                div[data-baseweb="select"] [role="option"] {
                    padding: 10px 12px !important;
                }
    
                /* Itens selecionados no dropdown */
                div[data-baseweb="select"] [role="option"][aria-selected="true"] {
                    background-color: rgba(139, 92, 246, 0.1) !important;
                    color: #7c3aed !important;
                }
                </style>
                """, unsafe_allow_html=True)
    
                # Lista de entes
                entes_disponiveis = [
                    "Câmara",
                    "Secretaria",
                    "Defensoria Pública", 
                    "Tribunal de Contas",
                    "Estatais",
                    "Sociedade Civil",
                    "Judiciário",
                    "Ministério Público"
                ]
    
                # Multiselect
                entes_selecionados = st.multiselect(
                    "",
                    options=entes_disponiveis,
                    label_visibility="collapsed",
                    key="entes_multiselect"
                )
    
                # Mostrar contador
                if entes_selecionados:
                    st.markdown(f'''
                    <div style="
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                        border: 1px solid #e2e8f0;
                        border-radius: 8px;
                        padding: 8px 12px;
                        margin-top: 8px;
                    ">
                        <span style="color: #475569; font-size: 13px; font-weight: 600;">
                            ✅ {len(entes_selecionados)} ente(s) selecionado(s)
                        </span>
                        <span style="color: #64748b; font-size: 13px;">
                            {', '.join(entes_selecionados)}
                        </span>
                    </div>
                    ''', unsafe_allow_html=True)
                
            # Seção 3: Localização
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">📍</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Localização</h3>
            </div>
            """, unsafe_allow_html=True)
            
            col9, col10 = st.columns(2)
            
            with col9:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Estado (UF)</div>', unsafe_allow_html=True)
                estado = st.selectbox("", options=[""] + opcoes['estados'], index=0, label_visibility="collapsed", key="estado_select")
            
            with col10:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Cidade *</div>', unsafe_allow_html=True)
                
                # Campo de texto SEMPRE habilitado, SEM restrições
                cidade = st.text_input(
                    "",
                    placeholder="Digite o nome da cidade",
                    key="cidade_input",
                    label_visibility="collapsed"
                )
                
                cidade_selecionada = cidade.strip() if cidade else ""
            
            # Seção 4: Origem e Interesse
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">🎯</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Origem e Interesse</h3>
            </div>
            """, unsafe_allow_html=True)
            
            col11, col12 = st.columns(2)
            
            with col11:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Origem do Lead</div>', unsafe_allow_html=True)
                origem_lead = st.selectbox("", options=[""] + opcoes['origens'], index=0, label_visibility="collapsed", key="origem_input")
            
            with col12:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Produto de Interesse</div>', unsafe_allow_html=True)
                produto_interesse = st.selectbox("", options=[""] + opcoes['produtos'], index=0, label_visibility="collapsed", key="produto_input")
            
            col13, col14 = st.columns(2)
            
            with col13:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Canal Preferido</div>', unsafe_allow_html=True)
                canal_preferido = st.selectbox("", options=[""] + opcoes['canais'], index=0, label_visibility="collapsed", key="canal_input")
            
            # Seção 5: Status e Classificação
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #ef4444 0%, #f87171 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">📊</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Status e Classificação</h3>
            </div>
            """, unsafe_allow_html=True)
            
            col15, col16 = st.columns(2)
            
            with col15:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Status</div>', unsafe_allow_html=True)
                status = st.selectbox("", options=[""] + opcoes['status'], index=1 if opcoes['status'] and "Novo" in opcoes['status'] else 0, label_visibility="collapsed", key="status_input")
            
            with col16:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Classificação</div>', unsafe_allow_html=True)
                classificacao = st.selectbox("", options=[""] + opcoes['classificacoes'], index=0, label_visibility="collapsed", key="classificacao_input")

            # Seção 6: Atribuição e Follow-up
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">👥</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Atribuição e Follow-up</h3>
            </div>
            """, unsafe_allow_html=True)
            
            col17, col18 = st.columns(2)
            
            with col17:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Atribuído a</div>', unsafe_allow_html=True)
                atribuido_a = st.selectbox("", options=[""] + opcoes['equipe'], index=0, label_visibility="collapsed", key="atribuido_input")
            
            with col18:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Tag</div>', unsafe_allow_html=True)
                tag = st.selectbox("", options=[""] + opcoes['tags'], index=0, label_visibility="collapsed", key="tag_input")
            
            col19, col20 = st.columns(2)
            
            with col19:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Data Próximo Contato</div>', unsafe_allow_html=True)
                data_proximo_contato = st.date_input("", value=None, key="data_proximo_input", label_visibility="collapsed")
            
            with col20:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Data Convertido</div>', unsafe_allow_html=True)
                data_convertido = st.date_input("", value=None, key="data_convertido_input", label_visibility="collapsed")
            
            # Seção 7: Preferências
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 12px; margin: 40px 0 30px 0; padding-bottom: 15px; border-bottom: 2px solid #f1f5f9;">
                <div style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%); color: white; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px;">📢</div>
                <h3 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0;">Preferências</h3>
            </div>
            """, unsafe_allow_html=True)
            
            col21, col22 = st.columns(2)
            
            with col21:
                st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin-bottom: 8px;">Receber Novidades</div>', unsafe_allow_html=True)
                receber_novidades = st.selectbox("", options=["", "Sim", "Não"], index=0, label_visibility="collapsed", key="novidades_input")
            
            # Observações
            st.markdown('<div style="color: #475569; font-size: 14px; font-weight: 600; margin: 40px 0 8px 0;">Observações</div>', unsafe_allow_html=True)
            observacoes = st.text_area("", placeholder="Observações adicionais...", label_visibility="collapsed", height=100, key="obs_input")
            
            # Botão de envio - Centralizado
            st.markdown('<div style="margin-top: 50px;"></div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                # Adicionar a classe gov-purple-btn ao redor do botão
                st.markdown('<div class="gov-purple-btn">', unsafe_allow_html=True)
                submitted = st.form_submit_button(
                    "🚀 **Cadastrar Lead**",
                    use_container_width=True,
                    help="Clique para adicionar este lead ao sistema"
                )
                st.markdown('</div>', unsafe_allow_html=True)
        
        # Processar envio do formulário
        if submitted:
            # Importar datetime ANTES de qualquer uso
            from datetime import datetime
            
            # Validação
            if not nome or not email:
                st.error("❌ **Campos obrigatórios:** Nome e e-mail são necessários!")
            elif not estado or estado.strip() == "":
                st.error("❌ **Campo obrigatório:** Selecione um Estado!")
            elif not cidade_selecionada or cidade_selecionada.strip() == "":
                st.error("❌ **Campo obrigatório:** Digite a Cidade!")
            elif not ente:
                st.error("❌ **Campo obrigatório:** Selecione pelo menos um Ente!")
            # VALIDAÇÃO DE CPF (apenas números)
            elif cpf and not cpf.replace('.', '').replace('-', '').replace(' ', '').isdigit():
                st.error("❌ **CPF inválido:** Digite apenas números!")
            # VALIDAÇÃO DE TELEFONE (apenas números)
            elif telefone and not telefone.replace('(', '').replace(')', '').replace(' ', '').replace('-', '').replace('+', '').isdigit():
                st.error("❌ **Telefone inválido:** Digite apenas números!")
            else:
                # GERAR O ID DO LEAD
                lead_id = f"L{datetime.now().strftime('%Y%m%d%H%M%S')}"
                
                # Converter datas para string (se elas existirem)
                data_proximo_str = ""
                data_convertido_str = ""
                
                # Verificar se as variáveis de data existem antes de usá-las
                try:
                    if data_proximo_contato:
                        data_proximo_str = data_proximo_contato.strftime("%Y-%m-%d")
                except NameError:
                    pass  # Variável não definida, mantém string vazia
                    
                try:
                    if data_convertido:
                        data_convertido_str = data_convertido.strftime("%Y-%m-%d")
                except NameError:
                    pass  # Variável não definida, mantém string vazia
                
                # Converter lista de entes para string separada por vírgula
                ente_str = ", ".join(ente) if ente else ""
                
                # Criar dicionário com os dados
                novo_lead = {
                    'ID': lead_id,
                    'Nome': nome,
                    'Email': email,
                    'CPF': limpar_numeros(cpf) if cpf else '',
                    'Telefone': limpar_numeros(telefone) if telefone else '',
                    'Cargo_Funcao': cargo if cargo else '',
                    'Ente': ente_str,
                    'Estado': estado if estado else '',
                    'Cidade': cidade_selecionada if cidade_selecionada else '',
                    'Origem_Lead': origem_lead if origem_lead else '',
                    'Produto_Interesse': produto_interesse if produto_interesse else '',
                    'Canal_Preferido': canal_preferido if canal_preferido else '',
                    'Status': status if status else 'Novo',
                    'Classificacao': classificacao if classificacao else '',
                    'Atribuido_A': atribuido_a if atribuido_a else '',
                    'Tag': tag if tag else '',
                    'Data_Proximo_Contato': data_proximo_str,
                    'Data_Convertido': data_convertido_str,
                    'Receber_Novidades': receber_novidades if receber_novidades else '',
                    'Observacoes': observacoes if observacoes else '',
                    'Data_Cadastro': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'Ultimo_Contato': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'Ultima_Acao': 'Cadastro via formulário'
                }
                
                # Salvar no Google Sheets
                sucesso = salvar_lead_no_google_sheets(novo_lead)
                
                if sucesso:
                    st.success("✅ Lead cadastrado com sucesso!")
                    st.balloons()
                    
                    # Adicionar botão para cadastrar novo lead
                    st.markdown('<div style="text-align: center; margin-top: 30px;">', unsafe_allow_html=True)
                    st.markdown('<div class="gov-purple-btn">', unsafe_allow_html=True)
                    if st.button("➕ Cadastrar Novo Lead", key="novo_lead_btn", use_container_width=True):
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

    elif menu == "Cursos":

        st.markdown('<div class="white-card">', unsafe_allow_html=True)

        st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 30px;">
            <div style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%); color: white; width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px;">🎓</div>
            <div>
                <h1 style="color: #1e293b; font-size: 28px; font-weight: 800; margin: 0;">Gestão de Cursos</h1>
                <p style="color: #64748b; font-size: 14px; margin: 5px 0 0 0;">Análise automática de participantes e desistências</p>
            </div>            
        """, unsafe_allow_html=True)

        # ==================== CARREGAR DADOS CORRETAMENTE ====================
        with st.spinner("🔄 Carregando dados em tempo real..."):
            df_leads = load_leads()
    
            # DESEMPACOTAR os 4 DataFrames!
            df_agosto, df_novembro, df_desistencias, df_desistencias_historico = importar_dados_cursos_automatico()
    
            # Juntar os dados de participantes (Agosto + Novembro)
            df_cursos_combinados = pd.concat([df_agosto, df_novembro], ignore_index=True)
    
            # Verificar se tem coluna 'PARTICIPOU', se não, criar baseada em alguma lógica
            if 'PARTICIPOU' not in df_cursos_combinados.columns:
                df_cursos_combinados['PARTICIPOU'] = 'SIM'

        # ==================== VERIFICAR SE TEM DADOS ====================
        # Verificar se há dados em qualquer uma das planilhas
        tem_dados_cursos = not df_cursos_combinados.empty
        tem_dados_desistencias = not df_desistencias.empty or not df_desistencias_historico.empty
    
        if not tem_dados_cursos and not tem_dados_desistencias:
            st.info("""
            ## 📭 Nenhum dado de cursos encontrado

            O sistema procurou automaticamente nas abas:

            ### 🎯 Abas de Participantes:
            - **"agosto"** (antiga "11 e 12 agosto")
            - **"novembro"** (antiga "17 e 18 Novembro")

            ### 🚫 Abas de Desistências:
            - **"desistencia_historico"** (antiga "Desistências - Histórico")
            - **"desistencia"** (antiga "Desistências")

            ### 🔍 Verifique:
            1. Se o arquivo **planilha.xlsx** está na pasta do projeto
            2. Se os nomes das abas estão: **agosto, novembro, desistencia, desistencia_historico**
            3. Se há dados nas abas
            """)

            st.markdown('</div>', unsafe_allow_html=True)
            return

        # ==================== CÁLCULOS PARA VISÃO GERAL ====================
        # 1. Total de registros únicos nas 4 planilhas
        # Juntar todas as 4 planilhas
        todas_planilhas = pd.concat([
            df_agosto, 
            df_novembro, 
            df_desistencias, 
            df_desistencias_historico
        ], ignore_index=True)
    
        # Remover duplicatas baseado em email (ou outra coluna única)
        # Ajuste a coluna conforme seus dados (ex: 'EMAIL', 'CPF', 'NOME')
        coluna_unica = None
        for col in ['EMAIL', 'CPF', 'NOME']:
            if col in todas_planilhas.columns:
                coluna_unica = col
                break
    
        if coluna_unica:
            total_registros = todas_planilhas[coluna_unica].nunique()
        else:
            # Se não encontrar coluna única, conta registros sem remover duplicatas
            total_registros = len(todas_planilhas)
    
        # 2. Participantes (já calculado corretamente)
        if 'PARTICIPOU' in df_cursos_combinados.columns:
            participantes = len(df_cursos_combinados[df_cursos_combinados['PARTICIPOU'] == 'SIM'])
        else:
            participantes = len(df_cursos_combinados)
    
        # 3. Desistências: soma de registros das duas planilhas de desistência
        # MAS EXCLUINDO quem já participou (Agosto ou Novembro)

        # Criar conjunto de pessoas que participaram (baseado em coluna única)
        if coluna_unica:
            # Pessoas que participaram (Agosto + Novembro)
            participantes_unicos = set(pd.concat([df_agosto, df_novembro], ignore_index=True)[coluna_unica].dropna().unique())
    
            # Pessoas nas planilhas de desistência
            desistentes_agosto = set(df_agosto[df_agosto['PARTICIPOU'] == 'NÃO'][coluna_unica].dropna().unique()) if 'PARTICIPOU' in df_agosto.columns else set()
            desistentes_novembro = set(df_novembro[df_novembro['PARTICIPOU'] == 'NÃO'][coluna_unica].dropna().unique()) if 'PARTICIPOU' in df_novembro.columns else set()
    
            desistentes_desistencias = set(df_desistencias[coluna_unica].dropna().unique()) if coluna_unica in df_desistencias.columns else set()
            desistentes_historico = set(df_desistencias_historico[coluna_unica].dropna().unique()) if coluna_unica in df_desistencias_historico.columns else set()
    
            # Juntar TODOS os desistentes
            todos_desistentes = desistentes_agosto.union(
                desistentes_novembro,
                desistentes_desistencias,
                desistentes_historico
            )
    
            # REMOVER quem já participou
            desistentes_nao_participantes = todos_desistentes - participantes_unicos
    
            # Contar desistências
            desistencias = len(desistentes_nao_participantes)
        else:
            # Se não tem coluna única, usar lógica simplificada
            # Contar desistentes das planilhas específicas
            desistencias = len(df_desistencias) + len(df_desistencias_historico)
    
        # 4. Municípios únicos nas 4 planilhas
        municipios_todas_planilhas = pd.concat([
            df_agosto[['MUNICIPIO']] if 'MUNICIPIO' in df_agosto.columns else pd.DataFrame(),
            df_novembro[['MUNICIPIO']] if 'MUNICIPIO' in df_novembro.columns else pd.DataFrame(),
            df_desistencias[['MUNICIPIO']] if 'MUNICIPIO' in df_desistencias.columns else pd.DataFrame(),
            df_desistencias_historico[['MUNICIPIO']] if 'MUNICIPIO' in df_desistencias_historico.columns else pd.DataFrame()
        ], ignore_index=True)
    
        if not municipios_todas_planilhas.empty and 'MUNICIPIO' in municipios_todas_planilhas.columns:
            municipios = municipios_todas_planilhas['MUNICIPIO'].nunique()
        else:
            municipios = 0

        # ==================== MÉTRICAS PRINCIPAIS ====================
        st.markdown("### 📊 Visão Geral")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Registros", total_registros)

        with col2:
            st.metric("Participantes", participantes)

        with col3:
            st.metric("Desistências", desistencias)

        with col4:
            st.metric("Municípios", municipios)


        # ==================== TABS DE ANÁLISE ====================
        tab1, tab2 = st.tabs([
            "👥 Participantes",  
            "🚫 Desistências"  
        ])
    
        with tab1:
            st.markdown("#### 👥 Participantes dos Cursos")
    
            if not df_cursos_combinados.empty:
                # Mostrar apenas quem participou (PARTICIPOU == 'SIM')
                if 'PARTICIPOU' in df_cursos_combinados.columns:
                    df_participantes = df_cursos_combinados[df_cursos_combinados['PARTICIPOU'] == 'SIM']
                else:
                    df_participantes = df_cursos_combinados

                # ==================== FILTRO COM ESTILO ALINHADO ====================
                st.markdown("##### 🔍 Pesquisar em qualquer campo")
        
                # Inicializar estado da sessão
                if 'pesquisa_participantes' not in st.session_state:
                    st.session_state.pesquisa_participantes = ""
        
                # CSS para alinhamento perfeito
                st.markdown("""
                <style>
                    /* Container principal flex */
                    .search-container {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        margin-bottom: 1rem;
                    }
            
                    /* Campo de pesquisa ocupa mais espaço */
                    .search-input {
                        flex-grow: 1;
                    }
            
                    /* Botão com altura fixa */
                    .search-button {
                        flex-shrink: 0;
                        width: 80px;
                    }
            
                    /* Esconde "Press Enter to apply" */
                    div[data-testid="InputInstructions"] {
                        display: none !important;
                    }
            
                    /* Ajusta altura do campo */
                    div[data-testid="stTextInput"] {
                        min-height: 52px;
                    }
            
                    /* Alinha verticalmente o conteúdo do campo */
                    div[data-testid="stTextInput"] > div > div {
                        align-items: center;
                    }
                </style>
                """, unsafe_allow_html=True)
        
                # HTML para layout perfeito
                st.markdown("""
                <div class="search-container">
                    <div class="search-input">
                """, unsafe_allow_html=True)
        
                # Campo de pesquisa
                pesquisa = st.text_input(
                    "Digite para pesquisar em TODAS as colunas:",
                    placeholder="Ex: São Paulo, João, Consultor X...",
                    value=st.session_state.pesquisa_participantes,
                    key="input_pesquisa_participantes_tab1",
                    label_visibility="collapsed"
                )
        
                st.markdown("</div><div class='search-button'>", unsafe_allow_html=True)
        
                # Botão Limpar
                if st.button("🧹 Limpar", 
                            key="limpar_participantes_tab1", 
                            use_container_width=True):
                    st.session_state.pesquisa_participantes = ""
                    st.rerun()
        
                st.markdown("</div></div>", unsafe_allow_html=True)
        
                # Atualizar estado e aplicar filtro em tempo real
                if pesquisa != st.session_state.pesquisa_participantes:
                    st.session_state.pesquisa_participantes = pesquisa
                    # Não precisa de rerun aqui, o filtro será aplicado abaixo
        
                # Aplicar filtro universal
                df_filtrado = df_participantes.copy()
        
                if st.session_state.pesquisa_participantes:
                    # Criar máscara para cada coluna
                    mascara = pd.Series([False] * len(df_filtrado))
            
                    for coluna in df_filtrado.columns:
                        # Converter para string e fazer busca case-insensitive
                        if df_filtrado[coluna].dtype == 'object':
                            mascara_coluna = df_filtrado[coluna].astype(str).str.contains(
                                st.session_state.pesquisa_participantes, 
                                case=False, 
                                na=False
                            )
                            mascara = mascara | mascara_coluna
            
                    df_filtrado = df_filtrado[mascara]
                    st.success(f"🔍 **{len(df_filtrado)} resultados para: '{st.session_state.pesquisa_participantes}'**")
                else:
                    st.info(f"📋 **{len(df_filtrado)} registros disponíveis**")
        
                st.dataframe(
                    df_filtrado,
                    use_container_width=True,
                    height=400,
                    hide_index=True
                )
        
        
                # Download button
                st.markdown("---")
                csv_data = df_filtrado.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Exportar Lista de Participantes",
                    data=csv_data,
                    file_name="participantes_cursos.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
            else:
                st.info("📭 Nenhum participante encontrado.")
    
        with tab2:
            st.markdown("#### 🚫 Desistências - Análise Detalhada")
    
            # ==================== COMBINAR DADOS DE DESISTÊNCIAS ====================
            df_desistencias_combinadas = pd.concat([df_desistencias, df_desistencias_historico], ignore_index=True)
    
            if not df_desistencias_combinadas.empty:
                # ==================== FILTRO COM ESTILO ALINHADO ====================
                st.markdown("##### 🔍 Pesquisar em qualquer campo")
        
                # Inicializar estado da sessão
                if 'pesquisa_desistencias' not in st.session_state:
                    st.session_state.pesquisa_desistencias = ""
        
                # CSS para alinhamento perfeito
                st.markdown("""
                <style>
                    /* Container principal flex */
                    .search-container {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        margin-bottom: 1rem;
                    }
            
                    /* Campo de pesquisa ocupa mais espaço */
                    .search-input {
                        flex-grow: 1;
                    }
            
                    /* Botão com altura fixa */
                    .search-button {
                        flex-shrink: 0;
                        width: 80px;
                    }
            
                    /* Esconde "Press Enter to apply" */
                    div[data-testid="InputInstructions"] {
                        display: none !important;
                    }
            
                    /* Ajusta altura do campo */
                    div[data-testid="stTextInput"] {
                        min-height: 52px;
                    }
            
                    /* Alinha verticalmente o conteúdo do campo */
                    div[data-testid="stTextInput"] > div > div {
                        align-items: center;
                    }
                </style>
                """, unsafe_allow_html=True)
        
                # HTML para layout perfeito
                st.markdown("""
                <div class="search-container">
                    <div class="search-input">
                """, unsafe_allow_html=True)
        
                # Campo de pesquisa
                pesquisa = st.text_input(
                    "Digite para pesquisar em TODAS as colunas:",
                    placeholder="Ex: São Paulo, motivo, Consultor Y...",
                    value=st.session_state.pesquisa_desistencias,
                    key="input_pesquisa_desistencias_tab2",
                    label_visibility="collapsed"
                )
        
                st.markdown("</div><div class='search-button'>", unsafe_allow_html=True)
        
                # Botão Limpar
                if st.button("🧹 Limpar", 
                            key="limpar_desistencias_tab2", 
                            use_container_width=True):
                    st.session_state.pesquisa_desistencias = ""
                    st.rerun()
        
                st.markdown("</div></div>", unsafe_allow_html=True)
        
                # Atualizar estado
                if pesquisa != st.session_state.pesquisa_desistencias:
                    st.session_state.pesquisa_desistencias = pesquisa
        
                # ==================== FILTRAR MUNICÍPIOS QUE NÃO PARTICIPARAM ====================
                df_base = df_desistencias_combinadas.copy()
        
                if not df_cursos_combinados.empty and 'MUNICIPIO' in df_cursos_combinados.columns:
                    # Padronizar nomes dos municípios
                    df_cursos_combinados['MUNICIPIO_CLEAN'] = df_cursos_combinados['MUNICIPIO'].astype(str).str.strip().str.upper()
                    df_base['MUNICIPIO_CLEAN'] = df_base['MUNICIPIO'].astype(str).str.strip().str.upper()
            
                    # Municípios que participaram
                    municipios_participantes = set(df_cursos_combinados['MUNICIPIO_CLEAN'].dropna())
            
                    # Filtrar desistências: apenas municípios que NÃO participaram
                    df_base = df_base[~df_base['MUNICIPIO_CLEAN'].isin(municipios_participantes)]
            
                    if 'MUNICIPIO_CLEAN' in df_base.columns:
                        df_base = df_base.drop(columns=['MUNICIPIO_CLEAN'])
        
                # ==================== APLICAR FILTRO DE PESQUISA ====================
                df_filtrado = df_base.copy()
        
                if st.session_state.pesquisa_desistencias:
                    # Criar máscara para cada coluna
                    mascara = pd.Series([False] * len(df_filtrado))
            
                    for coluna in df_filtrado.columns:
                        # Converter para string e fazer busca case-insensitive
                        if df_filtrado[coluna].dtype == 'object':
                            mascara_coluna = df_filtrado[coluna].astype(str).str.contains(
                                st.session_state.pesquisa_desistencias, 
                                case=False, 
                                na=False
                            )
                            mascara = mascara | mascara_coluna
            
                    df_filtrado = df_filtrado[mascara]
                    st.success(f"🔍 **{len(df_filtrado)} resultados para: '{st.session_state.pesquisa_desistencias}'**")
                else:
                    st.info(f"📋 **{len(df_filtrado)} registros de desistência**")
        
                # ==================== MOSTRAR TABELA ====================
                # Procurar coluna de motivo/objeção
                colunas_motivo = [col for col in df_filtrado.columns 
                                if any(termo in col.upper() for termo in ['MOTIVO_OBJECAO', 'MOTIVO', 'OBJEÇÃO', 'JUSTIFICATIVA', 'OBJECAO'])]
        
                if colunas_motivo:
                    coluna_motivo = colunas_motivo[0]
            
                    # Mostrar os dados principais
                    colunas_principais = ['MUNICIPIO', 'ENTE', 'CONSULTOR', 'SDR', coluna_motivo]
                    colunas_disponiveis = [col for col in colunas_principais if col in df_filtrado.columns]
            
                    st.dataframe(
                        df_filtrado[colunas_disponiveis],
                        use_container_width=True,
                        height=400,
                        hide_index=True
                    )
                else:
                    st.dataframe(
                        df_filtrado,
                        use_container_width=True,
                        height=400,
                        hide_index=True
                    )
        
                # ==================== BOTÃO DE DOWNLOAD ====================
                st.markdown("---")
                csv_data = df_filtrado.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Exportar Lista de Desistentes",
                    data=csv_data,
                    file_name="desistentes_filtrados.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
            else:
                st.info("📭 Nenhum registro de desistência encontrado.")              

    elif menu == "Relatórios":
        # Relatórios
        st.markdown('<div class="white-card">', unsafe_allow_html=True)
        st.subheader("Relatórios")
        st.info("Módulo de relatórios em desenvolvimento...")
        st.markdown('</div>', unsafe_allow_html=True)
        
if __name__ == "__main__":
    main()