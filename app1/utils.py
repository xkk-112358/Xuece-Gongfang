from cryptography.fernet import Fernet
from django.conf import settings

def get_encryption_key():
    """获取加密密钥（settings 中已强制要求配置，缺失会在启动时报错）"""
    # 确保密钥是URL安全的base64编码（Fernet需要base64编码的字节）
    return settings.URL_ENCRYPTION_KEY.encode('utf-8')

def encrypt_id(obj_id):
    """加密ID"""
    try:
        cipher = Fernet(get_encryption_key())
        token = cipher.encrypt(str(obj_id).encode('utf-8'))
        return token.decode('utf-8')
    except Exception as e:
        print(f"加密ID失败: {e}")
        return str(obj_id)

def decrypt_id(encrypted_id):
    """解密ID"""
    try:
        cipher = Fernet(get_encryption_key())
        token = encrypted_id.encode('utf-8') if isinstance(encrypted_id, str) else encrypted_id
        decrypted = cipher.decrypt(token).decode('utf-8')
        return int(decrypted)
    except Exception as e:
        print(f"解密ID失败: {e}")
        # 如果解密失败，尝试直接转换为整数（用于向后兼容）
        try:
            return int(encrypted_id)
        except:
            return None

def add_user_id_to_url(url, user):
    """为URL添加加密的user_id参数"""
    if user.is_authenticated:
        encrypted = encrypt_id(user.id)
        separator = '&' if '?' in url else '?'
        return f'{url}{separator}user_id={encrypted}'
    return url
