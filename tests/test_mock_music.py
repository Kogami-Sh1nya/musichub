import asyncio

from app.services.vk_music import VkMusicClient


def test_mock_music_flow():
    async def run():
        client = VkMusicClient("mock-access-100001")
        library = await client.get_library()
        assert library["count"] == 3

        result = await client.search("midnight")
        assert result["count"] == 1
        assert result["items"][0]["title"] == "Midnight City"

        await client.add(100001, 2)
        await client.delete(100001, 2)

        track = await client.get_by_id(100001, 2)
        assert track["items"][0]["artist"] == "M83"

    asyncio.run(run())
