"""Esquema estruturado que o modelo multimodal deve devolver."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PriceVariant(BaseModel):
    label: str = Field(description="Rótulo da variação, ex.: 'P', 'Grande', '500ml', 'Meia'")
    price: Optional[float] = Field(description="Preço da variação como número, sem símbolo de moeda")


class MenuItem(BaseModel):
    name: str = Field(description="Nome do prato/produto, como aparece no cardápio")
    description: Optional[str] = Field(description="Descrição/ingredientes, se houver")
    price: Optional[float] = Field(
        description="Preço único do item. null se o item só tiver preços por variação ou se o preço não estiver legível"
    )
    variants: list[PriceVariant] = Field(
        description="Variações de tamanho/porção com preços próprios. Lista vazia se não houver"
    )
    attributes: list[str] = Field(
        description="Atributos extras: 'vegetariano', 'vegano', 'picante', 'sem glúten', 'serve 2', 'novo', etc."
    )


class MenuCategory(BaseModel):
    name: str = Field(description="Nome da seção/categoria. Use 'Sem categoria' se não houver cabeçalho")
    items: list[MenuItem]


class MenuExtraction(BaseModel):
    is_menu: bool = Field(description="false se a imagem não for um cardápio")
    restaurant_name: Optional[str]
    currency: str = Field(description="Código ISO 4217 da moeda (BRL, USD, EUR...)")
    legibility: Literal["boa", "media", "ruim"] = Field(description="Legibilidade geral da imagem")
    notes: Optional[str] = Field(
        description="Problemas encontrados: partes cortadas, reflexo, texto ilegível, layout confuso"
    )
    categories: list[MenuCategory]
