from instagrapi import Client

# Troque pelas suas credenciais
usuario = input("Digite seu usuário do Instagram: ")
senha = input("Digite sua senha: ")

cl = Client()

try:
    cl.login(usuario, senha)
    cl.dump_settings("config_instagram.json")
    print("\n✅ Sessão salva com sucesso no arquivo: config_instagram.json")
    print("Agora você pode usar esse arquivo no seu app Flask com cl.load_settings()")
except Exception as e:
    print("\n❌ Erro ao fazer login:")
    print(str(e))
