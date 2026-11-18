// SPDX-License-Identifier: Apache-2.0
const appRoot = document.querySelector("base").getAttribute("app-root").replace(/\/$/, "");

document.addEventListener(
  "click",
  (event) => {
    if (event.target.closest("a.logout")) {
      event.preventDefault();
      event.stopPropagation();
      window.location.assign(`${appRoot}/logout`);
    }
  },
  true,
);

if (window.location.hash === "#/login") {
  window.location.hash = "";
}
