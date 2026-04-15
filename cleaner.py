import asyncio
from telethon import TelegramClient
from telethon.tl.types import User, Chat, Channel
from telethon.tl.functions.messages import DeleteHistoryRequest

API_ID   = 37551763
API_HASH = "8c78bb077ea6a9c45aba3e6dbfac51fe"

client = TelegramClient("session_cleaner", API_ID, API_HASH)

async def menu():
    print("\n" + "="*50)
    print("   TELEGRAM CLEANER")
    print("="*50)
    print("1. Lister tous mes chats")
    print("2. Archiver les chats deja lus")
    print("3. Muter tous les bots")
    print("4. TOUT faire en une fois")
    print("5. Supprimer tous les chats (sauf bots)")
    print("0. Quitter")
    print("="*50)
    choix = input("Ton choix : ").strip()

    if choix == "1":
        print("\nListe de tes chats :\n")
        async for dialog in client.iter_dialogs():
            e = dialog.entity
            if isinstance(e, User) and e.bot:
                t = "BOT"
            elif isinstance(e, User):
                t = "Personne"
            elif isinstance(e, Channel) and e.megagroup:
                t = "Groupe"
            elif isinstance(e, Channel):
                t = "Canal"
            else:
                t = "Autre"
            print(f"  {t:10} | Non lus: {dialog.unread_count:3} | {dialog.name}")

    elif choix == "2":
        count = 0
        async for dialog in client.iter_dialogs():
            if dialog.unread_count == 0 and not dialog.archived:
                await client.edit_folder(dialog, 1)
                print(f"  Archive : {dialog.name}")
                count += 1
        print(f"\nTermine ! {count} chats archives.")

    elif choix == "3":
        count = 0
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, User) and dialog.entity.bot:
                await client.edit_notify_settings(dialog, mute_until=2**31-1)
                print(f"  Mute : {dialog.name}")
                count += 1
        print(f"\nTermine ! {count} bots mutes.")

    elif choix == "4":
        print("\nArchivage des chats lus...")
        count = 0
        async for dialog in client.iter_dialogs():
            if dialog.unread_count == 0 and not dialog.archived:
                await client.edit_folder(dialog, 1)
                count += 1
        print(f"{count} chats archives.")
        print("Mutation des bots...")
        count = 0
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, User) and dialog.entity.bot:
                await client.edit_notify_settings(dialog, mute_until=2**31-1)
                count += 1
        print(f"{count} bots mutes.")
        print("\nNettoyage termine !")

    elif choix == "5":
        print("\n⚠️  ATTENTION : Cette action est IRREVERSIBLE !")
        confirm = input("Tape OUI pour confirmer la suppression de tous les chats (sauf bots) : ").strip()
        if confirm != "OUI":
            print("Annule.")
        else:
            count = 0
            errors = 0
            async for dialog in client.iter_dialogs():
                e = dialog.entity
                # Garder les bots
                if isinstance(e, User) and e.bot:
                    print(f"  Garde (bot) : {dialog.name}")
                    continue
                try:
                    if isinstance(e, User):
                        # Chat privé : supprimer l'historique des deux côtés
                        await client(DeleteHistoryRequest(
                            peer=dialog.input_entity,
                            max_id=0,
                            just_clear=False,
                            revoke=True
                        ))
                    elif isinstance(e, (Chat, Channel)):
                        # Groupes/Canaux : quitter
                        await client.delete_dialog(dialog)
                    print(f"  Supprime : {dialog.name}")
                    count += 1
                    await asyncio.sleep(0.5)  # éviter le flood ban
                except Exception as ex:
                    print(f"  Erreur ({dialog.name}) : {ex}")
                    errors += 1
            print(f"\nTermine ! {count} chats supprimes, {errors} erreurs.")

    elif choix == "0":
        print("Au revoir !")
        return

    await menu()

async def main():
    await client.start()
    print("Connecte a Telegram !")
    await menu()

with client:
    client.loop.run_until_complete(main())