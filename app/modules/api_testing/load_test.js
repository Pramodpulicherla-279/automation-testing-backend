import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 5 },   // ramp up to 20 users
    { duration: '30s', target: 5 },   // ramp up to 50 users
    { duration: '1m', target: 5 },   // ramp up to 100 users
    { duration: '2m', target: 5 },   // stay at 100 users
    { duration: '30s', target: 5 },   // ramp down to 50 users
    { duration: '30s', target: 0 },    // ramp down to 0 users
  ],
};

export default function () {
  http.get('https://fakestoreapi.com/products/1');

  sleep(1);
}