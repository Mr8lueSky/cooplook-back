import { registerRoute, initRouter, navigateTo } from './router.ts';
import { renderLogin } from './views/login.ts';
import { renderRooms } from './views/rooms.ts';
import { renderRoom } from './views/room.ts';

registerRoute('/login', renderLogin);
registerRoute('/rooms', renderRooms);
registerRoute('/room', renderRoom);
registerRoute('/', () => navigateTo('/rooms'));
registerRoute('*', () => navigateTo('/rooms'));

initRouter();
