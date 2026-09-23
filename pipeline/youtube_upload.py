"""Autenticação OAuth2 + upload de vídeo e thumbnail via YouTube Data API v3.

Cada canal (ver pipeline.channels) tem seu próprio client_secret.json e
youtube_token.json, isolados em secrets/<slug>/, permitindo manter várias
contas/canais publicando de forma independente na mesma máquina.

Antes de usar (por canal):
1. Crie um projeto no Google Cloud Console, ative a "YouTube Data API v3".
2. Gere credenciais OAuth2 do tipo "Desktop app" e baixe o client_secret.json -
   cole o conteúdo na interface de configuração (pipeline.settings_ui) ou
   salve manualmente em secrets/<slug>/client_secret.json.
3. Na primeira execução, uma janela do navegador vai pedir login/autorização
   com a conta daquele canal; o token fica salvo em
   secrets/<slug>/youtube_token.json para as próximas execuções não pedirem
   login de novo.
4. IMPORTANTE: no Google Cloud Console, deixe o app OAuth em modo "In
   production" (não "Testing") - em "Testing" o refresh token expira em 7
   dias e o upload automático para de funcionar sem aviso.

O campo de disclosure de "conteúdo sintético/alterado" (containsSyntheticMedia)
deve ser confirmado contra a versão mais recente da documentação oficial da
API antes de ir para produção - o nome/local exato do campo pode ter mudado
desde a pesquisa que embasou este projeto.
"""

from pathlib import Path

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config


def _has_required_scopes(creds: Credentials) -> bool:
    granted = set(creds.scopes or [])
    return set(config.YOUTUBE_UPLOAD_SCOPES).issubset(granted)


def _get_credentials(client_secret_path: Path, token_path: Path, force_new: bool = False) -> Credentials:
    creds = None
    if not force_new and token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(token_path), config.YOUTUBE_UPLOAD_SCOPES
        )
        # Token gerado com um escopo mais restrito (ex.: antes de este projeto
        # passar a exigir o escopo "youtube" completo pra listar/excluir
        # vídeos, não só publicar) - força reautorização em vez de seguir
        # usando um token que vai bater 403 "insufficient scopes" nas
        # chamadas novas.
        if not _has_required_scopes(creds):
            creds = None

    if force_new or not creds or not creds.valid:
        if not force_new and creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            if not client_secret_path.exists():
                raise RuntimeError(
                    f"Credenciais OAuth ausentes ({client_secret_path}). Cadastre o "
                    "client_secret.json desse canal pela interface de configuração antes de publicar."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), config.YOUTUBE_UPLOAD_SCOPES
            )
            # prompt=select_account força o Google a mostrar de novo a tela de
            # escolha de conta/canal (em vez de reusar silenciosamente a última
            # conta logada no navegador) - é o que evita reconectar sem querer
            # no canal pessoal errado quando o dono está tentando trocar pra um
            # Brand Account diferente.
            extra_kwargs = {"prompt": "select_account consent"} if force_new else {}
            creds = flow.run_local_server(port=0, **extra_kwargs)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds


def upload_video(video_path: Path, title: str, description: str,
                  tags: list[str], client_secret_path: Path, token_path: Path,
                  thumbnail_path: Path | None = None,
                  privacy_status: str = "private",
                  contains_synthetic_media: bool = True) -> str:
    creds = _get_credentials(client_secret_path, token_path)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "28",  # Science & Technology
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            # Disclosure de conteúdo alterado/sintético (narração e roteiro
            # gerados por IA) - ver nota no topo do arquivo sobre confirmar o
            # nome exato do campo contra a documentação mais recente da API.
            "selfCertifiedAsAltered": contains_synthetic_media,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()

    video_id = response["id"]

    if thumbnail_path is not None:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
        ).execute()

    return video_id


def list_channel_videos(client_secret_path: Path, token_path: Path, max_results: int = 50) -> list[dict]:
    """Lista os vídeos que JÁ existem no canal associado à conta autorizada -
    inclusive vídeos que não passaram por este pipeline (upload manual
    anterior, por exemplo). Usa o escopo "youtube" completo (não só
    "youtube.upload"), então exige reautorização se o token foi gerado antes
    dessa mudança."""
    creds = _get_credentials(client_secret_path, token_path)
    youtube = build("youtube", "v3", credentials=creds)

    channel_response = youtube.channels().list(part="contentDetails,snippet", mine=True).execute()
    items = channel_response.get("items", [])
    if not items:
        return []

    channel_info = items[0]
    uploads_playlist_id = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = []
    page_token = None
    while len(videos) < max_results:
        response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=min(50, max_results - len(videos)),
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "video_id": item["contentDetails"]["videoId"],
                "title": snippet["title"],
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail_url": (snippet.get("thumbnails", {}).get("default") or {}).get("url", ""),
            })
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return videos


def get_channel_info(client_secret_path: Path, token_path: Path) -> dict:
    """Dados básicos do canal associado à conta autorizada - nome, ID,
    contagem de vídeos/inscritos. Serve pra confirmar QUAL canal real do
    YouTube está conectado (o app não cria canal nenhum - ele só publica no
    canal padrão já existente da conta do Google que você autorizar; se essa
    conta ainda não tiver um canal do YouTube criado, é preciso criar um em
    youtube.com antes de autorizar aqui)."""
    creds = _get_credentials(client_secret_path, token_path)
    youtube = build("youtube", "v3", credentials=creds)
    response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    items = response.get("items", [])
    if not items:
        return {}
    ch = items[0]
    return {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "thumbnail_url": (ch["snippet"].get("thumbnails", {}).get("default") or {}).get("url", ""),
        "video_count": ch["statistics"].get("videoCount"),
        "subscriber_count": ch["statistics"].get("subscriberCount"),
        "view_count": ch["statistics"].get("viewCount"),
    }


def authorize_and_identify(client_secret_path: Path, token_path: Path, force_new: bool = False) -> dict:
    """Autoriza (abrindo o navegador se preciso) e IMEDIATAMENTE consulta qual
    canal real do YouTube ficou conectado, pra confirmação visível na
    interface - em vez de salvar o token silenciosamente e só descobrir
    depois que conectou no canal errado (esse foi um problema real relatado:
    o seletor de conta/canal do Google aparece durante o login, mas é fácil
    clicar sem querer no canal pessoal em destaque em vez do Brand Account
    desejado). `force_new=True` ignora qualquer token salvo e força a tela de
    escolha de conta/canal a aparecer de novo (prompt=select_account)."""
    creds = _get_credentials(client_secret_path, token_path, force_new=force_new)
    youtube = build("youtube", "v3", credentials=creds)
    response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    items = response.get("items", [])
    if not items:
        return {}
    ch = items[0]
    return {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "thumbnail_url": (ch["snippet"].get("thumbnails", {}).get("default") or {}).get("url", ""),
    }


def delete_video(video_id: str, client_secret_path: Path, token_path: Path) -> None:
    creds = _get_credentials(client_secret_path, token_path)
    youtube = build("youtube", "v3", credentials=creds)
    youtube.videos().delete(id=video_id).execute()
