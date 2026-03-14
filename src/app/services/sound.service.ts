// src/app/services/sound.service.ts
import { Injectable } from "@angular/core";

@Injectable({
  providedIn: "root",
})
export class SoundService {
  private readonly audioCache = new Map<string, HTMLAudioElement>();
  private isPrimed = false;
  private isPriming = false;

  constructor() {
    ["correct", "wrong", "win", "game-over"].forEach((name) => {
      const audio = new Audio(`assets/sounds/${name}.wav`);
      audio.preload = "auto";
      audio.load();
      this.audioCache.set(name, audio);
    });
  }

  private getOrCreateAudio(name: string): HTMLAudioElement {
    let audio = this.audioCache.get(name);
    if (!audio) {
      audio = new Audio(`assets/sounds/${name}.wav`);
      audio.preload = "auto";
      audio.load();
      this.audioCache.set(name, audio);
    }
    return audio;
  }

  primeFromUserGesture(): void {
    if (this.isPrimed || this.isPriming) {
      return;
    }

    this.isPriming = true;

    const audios = Array.from(this.audioCache.values());
    audios.forEach((audio) => {
      try {
        audio.muted = true;
        audio.currentTime = 0;
        const playPromise = audio.play();

        if (playPromise) {
          playPromise
            .then(() => {
              try {
                audio.pause();
                audio.currentTime = 0;
                audio.muted = false;
              } catch {}
            })
            .catch(() => {
              try {
                audio.muted = false;
                audio.currentTime = 0;
              } catch {}
            });
        } else {
          audio.muted = false;
          audio.currentTime = 0;
        }
      } catch {}
    });

    this.isPrimed = true;
    this.isPriming = false;
  }

  play(name: string) {
    const audio = this.getOrCreateAudio(name);

    try {
      audio.pause();
      audio.currentTime = 0;
      audio.muted = false;
    } catch {}

    const playPromise = audio.play();
    if (playPromise) {
      playPromise.catch((error) => {
        console.error(`Error playing sound '${name}':`, error);
      });
    }
  }

  playCorrect() {
    this.play("correct");
  }

  playWrong() {
    this.play("wrong");
  }

  playWin() {
    this.play("win");
  }

  playGameOver() {
    this.play("game-over");
  }
}
