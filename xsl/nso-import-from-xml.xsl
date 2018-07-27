<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
    <xsl:output method="xml" indent="yes" omit-xml-declaration="yes"/>
    <xsl:strip-space elements="*"/>

  <xsl:template match="/">
      <config xmlns="http://tail-f.com/ns/config/1.0">
        <devices xmlns="http://tail-f.com/ns/ncs">
          <device>
            <name><xsl:value-of select="$device_name"/></name>
            <config>
              <xsl:apply-templates select="@*|node()"/>
            </config>
          </device>
        </devices>
      </config>
  </xsl:template>

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- If in the XML file, omit the confd config tag from the results -->
  <xsl:template match="*[local-name()='config' and namespace-uri()='http://tail-f.com/ns/config/1.0']">
    <xsl:apply-templates select="@*|node()"/>
  </xsl:template>
</xsl:stylesheet>
