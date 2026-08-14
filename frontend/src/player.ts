import type { RoomSocket } from './ws.ts';
import { getVideoUrl } from './api.ts';

export interface PlayerState {
  isPlaying: boolean;
  currentTime: number;
  currentFileIndex: number;
}

export class SyncPlayer {
  private video: HTMLVideoElement;
  private roomId: string;
  private socket: RoomSocket;
  private state: PlayerState;
  private ignoreEventsUntil = 0;
  private seekDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private pauseDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private isLocalSeeking = false;

  constructor(
    videoEl: HTMLVideoElement,
    roomId: string,
    socket: RoomSocket,
    initialFi: number
  ) {
    this.video = videoEl;
    this.roomId = roomId;
    this.socket = socket;
    this.state = {
      isPlaying: false,
      currentTime: 0,
      currentFileIndex: initialFi,
    };
    this.bindEvents();
    this.bindSocket();
  }

  setSource(fi: number): void {
    this.state.currentFileIndex = fi;
    this.video.src = getVideoUrl(this.roomId, fi);
    this.video.currentTime = 0;
  }

  destroy(): void {
    this.video.pause();
    this.video.src = '';
    this.socket.onMessage(() => {});
    this.socket.onOpen(() => {});
    this.socket.onClose(() => {});
  }

  private bindEvents(): void {
    const v = this.video;

    v.addEventListener('play', () => {
      if (Date.now() < this.ignoreEventsUntil) return;
      this.socket.send(`up ${v.currentTime.toFixed(3)}`);
      this.socket.send(`pl ${v.currentTime.toFixed(3)}`);
    });

    v.addEventListener('pause', () => {
      if (Date.now() < this.ignoreEventsUntil) return;
      if (this.isLocalSeeking) return;
      if (this.pauseDebounceTimer) clearTimeout(this.pauseDebounceTimer);
      this.pauseDebounceTimer = setTimeout(() => {
        if (this.isLocalSeeking) return;
        this.socket.send(`pa ${v.currentTime.toFixed(3)}`);
      }, 50);
    });

    v.addEventListener('seeking', () => {
      if (Date.now() < this.ignoreEventsUntil) return;
      if (this.pauseDebounceTimer) {
        clearTimeout(this.pauseDebounceTimer);
        this.pauseDebounceTimer = null;
      }
      this.isLocalSeeking = true;
      if (this.seekDebounceTimer) clearTimeout(this.seekDebounceTimer);
      this.socket.send(`sp ${v.currentTime.toFixed(3)}`);
    });

    v.addEventListener('seeked', () => {
      if (!this.isLocalSeeking) return;
      if (this.seekDebounceTimer) clearTimeout(this.seekDebounceTimer);
      this.seekDebounceTimer = setTimeout(() => {
        this.socket.send(`up ${v.currentTime.toFixed(3)}`);
        this.isLocalSeeking = false;
      }, 150);
    });
  }

  private bindSocket(): void {
    this.socket.onMessage((cmd) => {
      switch (cmd.type) {
        case 'pl':
          this.applyIgnore(() => {
            this.video.currentTime = cmd.time;
            void this.video.play();
          });
          break;
        case 'pa':
          this.applyIgnore(() => {
            this.video.currentTime = cmd.time;
            this.video.pause();
          });
          break;
        case 'sp':
          this.applyIgnore(() => {
            this.video.currentTime = cmd.time;
            this.video.pause();
          });
          break;
        case 'cf':
          this.applyIgnore(() => {
            this.setSource(cmd.fi);
          });
          break;
      }
    });
  }

  private applyIgnore(fn: () => void): void {
    this.ignoreEventsUntil = Date.now() + 400;
    fn();
  }
}
