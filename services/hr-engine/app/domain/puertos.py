"""Puertos de la evaluación, de la coincidencia de skills y del alta de empresas: lo que el
dominio necesita del mundo exterior.

Los implementan los adaptadores de infraestructura (SQL, OpenAI, Gemini) y, en
los tests, adaptadores falsos. El dominio solo conoce estas firmas.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from app.domain.alta import SolicitudDeAlta
from app.domain.entidades import (
    Candidato,
    CvPendiente,
    Embedding,
    FitScore,
    PerfilAnonimo,
    ResultadoScoring,
    Vacante,
)


class ProveedorNoDisponibleError(RuntimeError):
    """El proveedor no puede atender ahora: caído, sin configurar, con timeouts,
    con 429/5xx o con el circuito abierto.

    Los adaptadores traducen a esta excepción los errores de disponibilidad de su
    SDK. Los demás fallos (una respuesta inválida, un 400) no se traducen: son
    errores de verdad y tienen que verse.
    """


class CandidateRepository(Protocol):
    """Lectura y escritura de candidatos, vacantes y applications de un tenant.

    Ve solo lo que deja ver el tenant de la sesión: un id de otra empresa se
    comporta como inexistente (`None`).
    """

    async def get_vacante(self, vacante_id: UUID) -> Vacante | None: ...

    async def get_candidato(self, candidato_id: UUID) -> Candidato | None: ...

    async def update_vacante_embedding(
        self, vacante_id: UUID, vector: tuple[float, ...]
    ) -> None: ...

    async def update_candidato_embedding(
        self, candidato_id: UUID, vector: tuple[float, ...]
    ) -> None: ...

    async def upsert_application(
        self,
        *,
        empresa_id: UUID,
        vacante_id: UUID,
        candidato_id: UUID,
        fit: FitScore,
    ) -> UUID:
        """Crea o actualiza la application (vacante, candidato) y devuelve su id."""
        ...


class EmbeddingProvider(Protocol):
    """Genera el embedding de un texto.

    Si el proveedor no está disponible lanza `ProveedorNoDisponibleError`. Los
    embeddings sirven a la búsqueda del sourcer, así que la evaluación sigue sin él.
    """

    async def embed(self, texto: str) -> Embedding: ...


class ScoringProvider(Protocol):
    """Puntúa el encaje de un perfil con un ICP.

    Recibe un `PerfilAnonimo` y no un `Candidato`: así el tipo impide que el
    nombre llegue al modelo. Si ningún modelo está disponible lanza
    `ProveedorNoDisponibleError`, y quien llama aplaza la evaluación.
    """

    async def score(self, perfil: PerfilAnonimo, icp: str) -> ResultadoScoring: ...


# ─── Coincidencia de skills del plan gratis (ADR-019) ────────────────────────


class CvInaccesibleError(LookupError):
    """El CV no se puede bajar y no se podrá después: no existe o pasa del tamaño máximo."""


class AlmacenNoDisponibleError(RuntimeError):
    """Storage no responde o rechaza la clave. El CV espera al siguiente barrido."""


class AlmacenDeCvs(Protocol):
    """Los CVs que subieron los candidatos. Solo existe del lado del servidor."""

    async def descargar(self, ruta: str) -> bytes: ...


class ExtractorDeTexto(Protocol):
    def extraer(self, contenido: bytes) -> str | None:
        """El texto del CV, o None si su formato no se puede leer (.doc, imagen, dañado)."""
        ...


class RepositorioDeCoincidencias(Protocol):
    """Las coincidencias y los CVs ilegibles, en el esquema `privado`."""

    async def pendientes(self, limite: int) -> list[CvPendiente]: ...

    async def guardar(self, cv: CvPendiente, encontradas: tuple[str, ...]) -> bool:
        """Guarda la coincidencia solo si la vacante sigue pidiendo `cv.skills`.

        Devuelve si la guardó. Al guardarla, el CV deja de estar marcado como ilegible.
        """
        ...

    async def marcar_ilegible(self, cv: CvPendiente) -> None: ...

    async def desmarcar_ilegible(self, cv: CvPendiente) -> None: ...


# ─── Alta de empresas (plan gratis) ──────────────────────────────────────────

#: Qué hay en Auth para un correo: nada, una invitación sin aceptar o una cuenta en uso.
EstadoDeCuenta = Literal["sin-cuenta", "pendiente", "confirmada"]


class CuentaYaExisteError(RuntimeError):
    """El correo ya tiene cuenta en Auth: no se le puede dar de alta otra vez."""


class InvitacionNoEnviadaError(RuntimeError):
    """Auth no mandó la invitación: caído, sin clave válida o con el límite de correos."""


class RepositorioDeAltas(Protocol):
    """Las empresas, sus invitaciones y las cuentas de Auth, con el rol dueño de la base."""

    async def estado_de_la_cuenta(self, correo: str) -> EstadoDeCuenta: ...

    async def crear_empresa_con_invitacion(
        self, solicitud: SolicitudDeAlta, slug: str, token_hash: str
    ) -> UUID | None:
        """Crea la empresa con plan gratis y su invitación, juntas y confirmadas.

        Devuelve el id de la empresa, o None si el slug ya es de otra.
        """
        ...

    async def deshacer(self, empresa_id: UUID) -> None:
        """Borra la empresa recién creada; su invitación se va en cascada."""
        ...


class ServicioDeInvitaciones(Protocol):
    """El correo de invitación de Supabase Auth. Solo del lado del servidor."""

    async def invitar(self, correo: str, token: str, nombre: str) -> None:
        """Crea la cuenta y manda el correo. `handle_new_user` (0003) la liga a su empresa
        con el token. Lanza `CuentaYaExisteError` o `InvitacionNoEnviadaError`."""
        ...

    async def reenviar(self, correo: str) -> None:
        """Vuelve a mandar el correo a una cuenta que todavía no entra."""
        ...
