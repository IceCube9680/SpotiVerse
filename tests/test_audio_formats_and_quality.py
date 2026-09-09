import unittest
import os
import shutil
import tempfile
import struct
import math
import wave
from unittest.mock import patch, MagicMock

import mutagen
from mutagen.id3 import ID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from config import Config
from utils.db import Database, _fallback_store
from utils.audio_formats import AudioFormat, AudioProfile
from utils.audio import AudioProcessor
from utils.feature_gates import FeatureGate
from handlers.commands import _settings_keyboard_for

class TestAudioFormatsAndQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="spotiverse_audio_test_")
        cls.sample_wav = os.path.join(cls.test_dir, "sample_input.wav")
        cls._create_synthetic_wav(cls.sample_wav, duration_sec=1.0)
        cls.processor = AudioProcessor()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        self.db = Database(connect=False)
        self.db.available = False
        _fallback_store["users"].clear()
        _fallback_store["downloads"].clear()
        _fallback_store["bot_settings"].clear()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def _create_synthetic_wav(path: str, duration_sec: float = 1.0, sample_rate: int = 44100):
        """Create a valid 440Hz sine wave WAV file using standard library wave module"""
        n_samples = int(duration_sec * sample_rate)
        with wave.open(path, "w") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            raw_frames = bytearray()
            for i in range(n_samples):
                val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
                raw_frames.extend(struct.pack("<h", val))
            wav_file.writeframes(raw_frames)

    def test_audio_profile_allowed_formats(self):
        free_fmts = AudioProfile.get_allowed_formats(is_premium=False)
        self.assertIn("mp3", free_fmts)
        self.assertNotIn("flac", free_fmts)
        self.assertNotIn("wav", free_fmts)

        prem_fmts = AudioProfile.get_allowed_formats(is_premium=True)
        for fmt in ["mp3", "flac", "m4a", "ogg", "wav"]:
            self.assertIn(fmt, prem_fmts)

    def test_audio_profile_allowed_qualities(self):
        mp3_q = AudioProfile.get_allowed_qualities("mp3", is_premium=True)
        self.assertEqual(mp3_q, [64, 128, 192, 256, 320])

        m4a_q = AudioProfile.get_allowed_qualities("m4a", is_premium=True)
        self.assertEqual(m4a_q, [128, 192, 256, 320])

        ogg_q = AudioProfile.get_allowed_qualities("ogg", is_premium=True)
        self.assertEqual(ogg_q, [64, 96, 128, 160, 192, 256, 320])

        wav_q = AudioProfile.get_allowed_qualities("wav", is_premium=True)
        self.assertEqual(wav_q, [
            "16-bit 44.1kHz", "16-bit 48kHz",
            "24-bit 44.1kHz", "24-bit 48kHz", "24-bit 96kHz"
        ])

    def test_audio_profile_wav_parsing(self):
        depth, rate = AudioProfile.parse_wav_quality("16-bit 44.1kHz")
        self.assertEqual(depth, 16)
        self.assertEqual(rate, 44100)

        depth, rate = AudioProfile.parse_wav_quality("24-bit 96kHz")
        self.assertEqual(depth, 24)
        self.assertEqual(rate, 96000)

    def test_ffmpeg_args_generation(self):
        args_mp3 = AudioProfile.get_ffmpeg_args("ffmpeg", "in.wav", "out.mp3", "mp3", 320)
        self.assertIn("libmp3lame", args_mp3)
        self.assertIn("320k", args_mp3)

        args_flac = AudioProfile.get_ffmpeg_args("ffmpeg", "in.wav", "out.flac", "flac", "high")
        self.assertIn("flac", args_flac)

        args_m4a = AudioProfile.get_ffmpeg_args("ffmpeg", "in.wav", "out.m4a", "m4a", 256)
        self.assertIn("aac", args_m4a)
        self.assertIn("256k", args_m4a)

        args_ogg = AudioProfile.get_ffmpeg_args("ffmpeg", "in.wav", "out.ogg", "ogg", 192)
        self.assertIn("libvorbis", args_ogg)
        self.assertIn("-q:a", args_ogg)

        args_wav = AudioProfile.get_ffmpeg_args("ffmpeg", "in.wav", "out.wav", "wav", "24-bit 96kHz")
        self.assertIn("pcm_s24le", args_wav)
        self.assertIn("96000", args_wav)

    def test_convert_all_mp3_qualities(self):
        for q in [64, 128, 192, 256, 320]:
            out_file = os.path.join(self.test_dir, f"out_test_{q}.mp3")
            ok = self.processor.convert_audio(self.sample_wav, out_file, "mp3", q)
            self.assertTrue(ok, f"Failed converting to MP3 {q}k")
            self.assertTrue(os.path.exists(out_file))
            self.assertGreater(os.path.getsize(out_file), 0)

    def test_convert_flac_levels(self):
        for lvl in ["low", "medium", "high"]:
            out_file = os.path.join(self.test_dir, f"out_test_{lvl}.flac")
            ok = self.processor.convert_audio(self.sample_wav, out_file, "flac", lvl)
            self.assertTrue(ok, f"Failed converting to FLAC {lvl}")
            self.assertTrue(os.path.exists(out_file))
            self.assertGreater(os.path.getsize(out_file), 0)

    def test_convert_all_m4a_qualities(self):
        for q in [128, 192, 256, 320]:
            out_file = os.path.join(self.test_dir, f"out_test_{q}.m4a")
            ok = self.processor.convert_audio(self.sample_wav, out_file, "m4a", q)
            self.assertTrue(ok, f"Failed converting to M4A {q}k")
            self.assertTrue(os.path.exists(out_file))
            self.assertGreater(os.path.getsize(out_file), 0)

    def test_convert_all_ogg_qualities(self):
        for q in [64, 96, 128, 160, 192, 256, 320]:
            out_file = os.path.join(self.test_dir, f"out_test_{q}.ogg")
            ok = self.processor.convert_audio(self.sample_wav, out_file, "ogg", q)
            self.assertTrue(ok, f"Failed converting to OGG {q}k")
            self.assertTrue(os.path.exists(out_file))
            self.assertGreater(os.path.getsize(out_file), 0)

    def test_convert_all_wav_qualities(self):
        for q_label in ["16-bit 44.1kHz", "16-bit 48kHz", "24-bit 44.1kHz", "24-bit 48kHz", "24-bit 96kHz"]:
            clean_name = q_label.replace(" ", "_").replace(".", "_")
            out_file = os.path.join(self.test_dir, f"out_test_{clean_name}.wav")
            ok = self.processor.convert_audio(self.sample_wav, out_file, "wav", q_label)
            self.assertTrue(ok, f"Failed converting to WAV {q_label}")
            self.assertTrue(os.path.exists(out_file))
            self.assertGreater(os.path.getsize(out_file), 0)

    def test_metadata_embedding_across_all_formats(self):
        meta = {
            "title": "Quantum Symphony",
            "artist": "Nova Sonic",
            "album": "Cosmic Drift",
            "year": "2026",
            "genre": "Synthwave"
        }

        # 1. MP3
        mp3_file = os.path.join(self.test_dir, "meta_test.mp3")
        self.processor.convert_audio(self.sample_wav, mp3_file, "mp3", 320)
        self.processor.add_metadata(mp3_file, meta)
        id3_tag = ID3(mp3_file)
        self.assertEqual(id3_tag["TIT2"].text[0], "Quantum Symphony")
        self.assertEqual(id3_tag["TPE1"].text[0], "Nova Sonic")

        # 2. FLAC
        flac_file = os.path.join(self.test_dir, "meta_test.flac")
        self.processor.convert_audio(self.sample_wav, flac_file, "flac", "high")
        self.processor.add_metadata(flac_file, meta)
        flac_tag = FLAC(flac_file)
        self.assertEqual(flac_tag["title"][0], "Quantum Symphony")
        self.assertEqual(flac_tag["artist"][0], "Nova Sonic")

        # 3. M4A
        m4a_file = os.path.join(self.test_dir, "meta_test.m4a")
        self.processor.convert_audio(self.sample_wav, m4a_file, "m4a", 256)
        self.processor.add_metadata(m4a_file, meta)
        m4a_tag = MP4(m4a_file)
        self.assertEqual(m4a_tag.tags["\xa9nam"][0], "Quantum Symphony")
        self.assertEqual(m4a_tag.tags["\xa9ART"][0], "Nova Sonic")

        # 4. OGG
        ogg_file = os.path.join(self.test_dir, "meta_test.ogg")
        self.processor.convert_audio(self.sample_wav, ogg_file, "ogg", 192)
        self.processor.add_metadata(ogg_file, meta)
        ogg_tag = OggVorbis(ogg_file)
        self.assertEqual(ogg_tag["title"][0], "Quantum Symphony")
        self.assertEqual(ogg_tag["artist"][0], "Nova Sonic")

        # 5. WAV
        wav_file = os.path.join(self.test_dir, "meta_test.wav")
        self.processor.convert_audio(self.sample_wav, wav_file, "wav", "16-bit 44.1kHz")
        ok_wav = self.processor.add_metadata(wav_file, meta)
        self.assertTrue(ok_wav)

    def test_source_quality_probing_and_non_upscaling(self):
        info = self.processor.get_source_quality(self.sample_wav)
        self.assertEqual(info["sample_rate"], 44100)
        self.assertEqual(info["channels"], 1)

        # Convert asking for 320k
        out_mp3 = os.path.join(self.test_dir, "test_probe.mp3")
        ok = self.processor.convert_audio(self.sample_wav, out_mp3, "mp3", 320)
        self.assertTrue(ok)
        self.assertIsNotNone(self.processor.last_conversion_info.get("source_quality"))
        self.assertGreater(self.processor.last_conversion_info.get("conversion_duration_sec", 0), 0)

    def test_file_size_validation(self):
        valid, size_mb = self.processor.validate_file_size(self.sample_wav, max_mb=50)
        self.assertTrue(valid)
        self.assertGreater(size_mb, 0)

        # Artificial tiny limit to trigger limit
        valid_tiny, _ = self.processor.validate_file_size(self.sample_wav, max_mb=0.00001)
        self.assertFalse(valid_tiny)

    def test_feature_gate_format_and_quality_entitlements(self):
        free_uid = 1001
        prem_uid = 2002

        self.db.update_user(free_uid, {"premium": False})
        self.db.update_user(prem_uid, {"premium": True, "lifetime_premium": True})

        # Free user requesting FLAC gets downgraded to MP3
        res_free = FeatureGate.authorize_download(free_uid, requested_format="flac")
        self.assertTrue(res_free.allowed)
        self.assertEqual(res_free.effective_format, "mp3")

        # Free user requesting WAV gets downgraded to MP3
        res_free_wav = FeatureGate.authorize_download(free_uid, requested_format="wav")
        self.assertTrue(res_free_wav.allowed)
        self.assertEqual(res_free_wav.effective_format, "mp3")

        # Premium user requesting FLAC gets FLAC
        res_prem_flac = FeatureGate.authorize_download(prem_uid, requested_format="flac")
        self.assertTrue(res_prem_flac.allowed)
        self.assertEqual(res_prem_flac.effective_format, "flac")

        # Premium user requesting M4A gets M4A
        res_prem_m4a = FeatureGate.authorize_download(prem_uid, requested_format="m4a")
        self.assertTrue(res_prem_m4a.allowed)
        self.assertEqual(res_prem_m4a.effective_format, "m4a")

        # Premium user requesting WAV gets WAV
        res_prem_wav = FeatureGate.authorize_download(prem_uid, requested_format="wav")
        self.assertTrue(res_prem_wav.allowed)
        self.assertEqual(res_prem_wav.effective_format, "wav")

    def test_settings_keyboard_rendering_free_vs_premium(self):
        free_user = {"user_id": 1001, "premium": False, "preferred_format": "mp3", "preferred_quality": 320}
        prem_user = {"user_id": 2002, "premium": True, "preferred_format": "mp3", "preferred_quality": 320}

        kb_free = _settings_keyboard_for(free_user)
        self.assertIsNotNone(kb_free)
        # Should have upgrade button for free user
        btn_texts = [btn.text for row in kb_free.inline_keyboard for btn in row]
        self.assertTrue(any("Unlock Lossless" in t for t in btn_texts))

        kb_prem = _settings_keyboard_for(prem_user)
        prem_btn_texts = [btn.text for row in kb_prem.inline_keyboard for btn in row]
        # Should have format cycling indicator
        self.assertTrue(any("Format: MP3 → FLAC" in t for t in prem_btn_texts))

    def test_database_multi_format_statistics_aggregation(self):
        # Record attempts in different formats
        self.db.record_download_attempt(
            user_id=101, provider="spotify", status="success", format_used="mp3", quality=320,
            file_size=8 * 1024 * 1024, duration=180, conversion_duration=0.5
        )
        self.db.record_download_attempt(
            user_id=102, provider="youtube", status="success", format_used="flac", quality="high",
            file_size=25 * 1024 * 1024, duration=180, conversion_duration=1.2
        )
        self.db.record_download_attempt(
            user_id=103, provider="jiosaavn", status="success", format_used="m4a", quality=256,
            file_size=6 * 1024 * 1024, duration=180, conversion_duration=0.4
        )
        self.db.record_download_attempt(
            user_id=104, provider="soundcloud", status="success", format_used="ogg", quality=192,
            file_size=5 * 1024 * 1024, duration=180, conversion_duration=0.3
        )
        self.db.record_download_attempt(
            user_id=105, provider="deezer", status="success", format_used="wav", quality="24-bit 96kHz",
            file_size=40 * 1024 * 1024, duration=180, conversion_duration=2.0
        )
        # 1 failed download for M4A
        self.db.record_download_attempt(
            user_id=106, provider="youtube", status="failed", format_used="m4a", quality=320,
            error="Conversion timeout"
        )

        stats = self.db.get_statistics("30d")
        self.assertEqual(stats["total_downloads"], 6)
        self.assertEqual(stats["successful_downloads"], 5)
        self.assertEqual(stats["failed_downloads"], 1)
        self.assertEqual(stats["format_usage"]["mp3"], 1)
        self.assertEqual(stats["format_usage"]["flac"], 1)
        self.assertEqual(stats["format_usage"]["m4a"], 1)
        self.assertEqual(stats["format_usage"]["ogg"], 1)
        self.assertEqual(stats["format_usage"]["wav"], 1)
        self.assertEqual(stats["failed_conversions_by_format"]["m4a"], 1)
        self.assertGreater(stats["avg_conversion_duration_sec"], 0.0)
        self.assertGreater(stats["avg_output_size_mb"], 0.0)

if __name__ == "__main__":
    unittest.main()
